"""Scopus scraping utilities powered by Playwright."""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from playwright.async_api import (  # type: ignore
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)


SCOPUS_BASE_URL = "https://www.scopus.com"
SOURCES_PAGE = f"{SCOPUS_BASE_URL}/sources.uri"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class ScopusScraperError(RuntimeError):
    """Raised when the Scopus scraper is unable to retrieve the requested data."""


@dataclass
class QuartileInfo:
    subject: str
    quartile: str


@dataclass
class ScopusMetrics:
    issn: str
    title: str
    cite_score: Optional[str]
    snip: Optional[str]
    sjr: Optional[str]
    quartiles: List[QuartileInfo]
    source_url: Optional[str]

    def as_dict(self) -> Dict[str, object]:
        return {
            "issn": self.issn,
            "title": self.title,
            "citeScore": self.cite_score,
            "snip": self.snip,
            "sjr": self.sjr,
            "quartiles": [quartile.__dict__ for quartile in self.quartiles],
            "sourceUrl": self.source_url,
        }


async def fetch_scopus_metrics_async(
    issn: str,
    *,
    cookie_header: Optional[str] = None,
    headless: bool = True,
    timeout: int = 30,
) -> ScopusMetrics:
    """Fetch metrics for a given ISSN from Scopus using Playwright.

    Parameters
    ----------
    issn: str
        The ISSN to look up.
    cookie_header: Optional[str]
        Optional raw cookie header to include for authenticated sessions.
    headless: bool
        Whether to launch the browser in headless mode.
    timeout: int
        Timeout (in seconds) for navigation and selector waits.

    Returns
    -------
    ScopusMetrics
        The metrics discovered for the source.
    """

    sanitized_issn = issn.strip()
    if not sanitized_issn:
        raise ScopusScraperError("ISSN must not be empty.")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-US",
            color_scheme="dark",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        if cookie_header:
            cookies = _parse_cookie_header(cookie_header)
            if cookies:
                await context.add_cookies(cookies)

        page = await context.new_page()
        try:
            await page.goto(SOURCES_PAGE, wait_until="networkidle", timeout=timeout * 1000)
        except PlaywrightTimeoutError as exc:  # pragma: no cover - network heavy
            raise ScopusScraperError("Unable to load Scopus sources directory.") from exc

        await _accept_consent_banner(page)
        await _fill_issn_and_submit(page, sanitized_issn, timeout)

        await page.wait_for_timeout(1500)  # allow table to update
        row_locator = page.locator(f"tr:has-text(\"{sanitized_issn}\")")
        if await row_locator.count() == 0:
            raise ScopusScraperError(f"No results found for ISSN {sanitized_issn}.")

        row_element = row_locator.first
        table_data = await _extract_table_row(page, row_element)

        detail_metrics: Optional[ScopusMetrics] = None
        detail_page = await _open_detail_page_if_available(context, row_element)
        if detail_page is not None:
            try:
                detail_metrics = await _parse_detail_page(detail_page, sanitized_issn, timeout)
            finally:
                await detail_page.close()

        await context.close()
        await browser.close()

    if detail_metrics is not None:
        # Combine table data with detail page metrics, preferring detail page info.
        cite_score = detail_metrics.cite_score or table_data.get("citescore")
        snip = detail_metrics.snip or table_data.get("snip")
        sjr = detail_metrics.sjr or table_data.get("sjr")
        title = detail_metrics.title or table_data.get("title", "")
        quartiles = detail_metrics.quartiles
        source_url = detail_metrics.source_url
    else:
        cite_score = table_data.get("citescore")
        snip = table_data.get("snip")
        sjr = table_data.get("sjr")
        title = table_data.get("title", "")
        quartiles = table_data.get("quartiles", [])
        source_url = table_data.get("source_url")

    quartile_objects: List[QuartileInfo] = []
    for item in quartiles:
        if isinstance(item, QuartileInfo):
            quartile_objects.append(item)
        elif isinstance(item, dict) and "subject" in item and "quartile" in item:
            quartile_objects.append(QuartileInfo(subject=item["subject"], quartile=item["quartile"]))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            quartile_objects.append(QuartileInfo(subject=str(item[0]), quartile=str(item[1])))


    return ScopusMetrics(
        issn=sanitized_issn,
        title=title,
        cite_score=cite_score,
        snip=snip,
        sjr=sjr,
        quartiles=quartile_objects,
        source_url=source_url,
    )


def fetch_scopus_metrics(
    issn: str,
    *,
    cookie_header: Optional[str] = None,
    headless: Optional[bool] = None,
    timeout: Optional[int] = None,
) -> Dict[str, object]:
    """Synchronous wrapper around :func:`fetch_scopus_metrics_async`."""

    resolved_headless = True if headless is None else headless
    resolved_timeout = int(timeout) if timeout is not None else int(os.getenv("SCOPUS_TIMEOUT", "30"))

    return asyncio.run(
        fetch_scopus_metrics_async(
            issn,
            cookie_header=cookie_header,
            headless=resolved_headless,
            timeout=resolved_timeout,
        )
    ).as_dict()


def _parse_cookie_header(cookie_header: str) -> List[Dict[str, object]]:
    cookies: List[Dict[str, object]] = []
    parts = [segment.strip() for segment in cookie_header.split(";") if segment.strip()]
    for part in parts:
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".scopus.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
            }
        )
    return cookies


async def _accept_consent_banner(page) -> None:
    try:
        await page.locator("button#onetrust-accept-btn-handler").click(timeout=4000)
    except PlaywrightTimeoutError:
        return


async def _fill_issn_and_submit(page, issn: str, timeout: int) -> None:
    input_selectors = [
        "input[name='issn']",
        "input#issn",
        "input[data-test='issn-input']",
        "input[placeholder*='ISSN']",
    ]
    field_found = False
    for selector in input_selectors:
        locator = page.locator(selector)
        try:
            await locator.wait_for(timeout=timeout * 1000)
        except PlaywrightTimeoutError:
            continue
        await locator.fill(issn)
        field_found = True
        try:
            await locator.press("Enter")
        except PlaywrightTimeoutError:
            pass
        break

    if not field_found:
        raise ScopusScraperError("Could not locate ISSN input field on Scopus page.")

    button_selectors = [
        "button:has-text('Search')",
        "button[type='submit']",
        "[data-test='search-button']",
    ]
    for selector in button_selectors:
        try:
            await page.locator(selector).click(timeout=2000)
            return
        except PlaywrightTimeoutError:
            continue


async def _extract_table_row(page, row_locator) -> Dict[str, object]:
    table_info = await page.evaluate(
        """
        (row) => {
            const table = row.closest('table');
            if (!table) {
                return {};
            }
            const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim().toLowerCase());
            const cells = Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim());
            const result = {};
            headers.forEach((header, index) => {
                const value = cells[index] || '';
                if (header.includes('source title')) {
                    result.title = value;
                }
                if (header.includes('citescore')) {
                    result.citescore = value;
                }
                if (header.includes('snip')) {
                    result.snip = value;
                }
                if (header.includes('sjr')) {
                    result.sjr = value;
                }
                if (header.includes('issn')) {
                    result.issn = value;
                }
                if (header.includes('quartile')) {
                    result.quartileHint = value;
                }
            });

            const areaColumnIndex = headers.findIndex(header => header.includes('subject area'));
            if (areaColumnIndex !== -1) {
                const areaValue = cells[areaColumnIndex];
                if (areaValue) {
                    const quartiles = [];
                    const sections = areaValue.split(/\n|,|;/).map(item => item.trim()).filter(Boolean);
                    for (const section of sections) {
                        const match = section.match(/(.*?)(Q[1-4])/i);
                        if (match) {
                            quartiles.push({ subject: match[1].trim(), quartile: match[2].toUpperCase() });
                        }
                    }
                    if (quartiles.length) {
                        result.quartiles = quartiles;
                    }
                }
            }

            const link = row.querySelector('a[href*="sourceid"], a[href*="sources"]');
            if (link && link.href) {
                result.source_url = link.href;
            }
            return result;
        }
        """,
        row_locator,
    )
    return table_info or {}


async def _open_detail_page_if_available(context, row_locator):
    link_locator = row_locator.locator("a[href*='sourceid']").first
    if await link_locator.count() == 0:
        return None

    try:
        async with context.expect_page() as detail_page_info:
            await link_locator.click()
        detail_page = await detail_page_info.value
        await detail_page.wait_for_load_state("domcontentloaded")
        return detail_page
    except PlaywrightTimeoutError:
        return None


async def _parse_detail_page(page, issn: str, timeout: int) -> ScopusMetrics:
    try:
        await page.wait_for_timeout(1500)
    except PlaywrightTimeoutError:
        pass

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title_from_detail(soup)
    cite_score = _extract_metric(soup, "CiteScore")
    snip = _extract_metric(soup, "SNIP")
    sjr = _extract_metric(soup, "SJR")
    quartiles = _extract_quartiles(soup)
    source_url = page.url

    quartile_objects = [QuartileInfo(subject=item[0], quartile=item[1]) for item in quartiles]

    return ScopusMetrics(
        issn=issn,
        title=title,
        cite_score=cite_score,
        snip=snip,
        sjr=sjr,
        quartiles=quartile_objects,
        source_url=source_url,
    )


def _extract_title_from_detail(soup: BeautifulSoup) -> str:
    title_tag = soup.find("h1")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)
    meta_title = soup.find("meta", attrs={"property": "og:title"})
    if meta_title and meta_title.get("content"):
        return meta_title["content"].strip()
    return ""


def _extract_metric(soup: BeautifulSoup, label: str) -> Optional[str]:
    pattern = re.compile(rf"{re.escape(label)}\\s*:?\\s*([0-9]+(?:\\.[0-9]+)?)", re.IGNORECASE)
    text_nodes = soup.find_all(string=pattern)
    for node in text_nodes:
        match = pattern.search(node)
        if match:
            return match.group(1)
    # Sometimes the value can be in a sibling element
    label_element = soup.find(lambda tag: tag.get_text(strip=True).lower().startswith(label.lower()))
    if label_element:
        sibling_text = label_element.find_next(string=re.compile(r"[0-9]"))
        if sibling_text:
            match = re.search(r"([0-9]+(?:\\.[0-9]+)?)", sibling_text)
            if match:
                return match.group(1)
    return None


def _extract_quartiles(soup: BeautifulSoup) -> List[List[str]]:
    quartiles: List[List[str]] = []
    quartile_pattern = re.compile(r"(Q[1-4])", re.IGNORECASE)
    for element in soup.find_all(string=quartile_pattern):
        parent_text = element.parent.get_text(" ", strip=True)
        match = re.search(r"(.+?)\\s*(Q[1-4])", parent_text, re.IGNORECASE)
        if match:
            subject = match.group(1).strip()
            quartile = match.group(2).upper()
            if subject and quartile:
                entry = [subject, quartile]
                if entry not in quartiles:
                    quartiles.append(entry)
    return quartiles


__all__ = [
    "ScopusScraperError",
    "ScopusMetrics",
    "QuartileInfo",
    "fetch_scopus_metrics",
    "fetch_scopus_metrics_async",
]
