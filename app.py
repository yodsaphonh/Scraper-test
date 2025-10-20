"""Flask application that provides a web UI for Scopus metrics scraping."""
from __future__ import annotations

import os
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from scraper import ScopusScraperError, fetch_scopus_metrics

load_dotenv()

app = Flask(__name__)

DEFAULT_COOKIE = os.getenv("SCOPUS_COOKIE", "")
DEFAULT_HEADLESS = os.getenv("SCOPUS_HEADLESS", "true").lower() != "false"


@app.route("/")
def index():
    return render_template(
        "index.html",
        default_cookie=DEFAULT_COOKIE,
        headless=DEFAULT_HEADLESS,
    )


@app.post("/api/scrape")
def scrape_metrics() -> Any:
    payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    issn = (payload.get("issn") or "").strip()
    cookie_header = (payload.get("cookie") or DEFAULT_COOKIE or "").strip() or None
    headless_flag = payload.get("headless")
    headless = DEFAULT_HEADLESS if headless_flag is None else bool(headless_flag)

    if not issn:
        return jsonify({"success": False, "message": "กรุณากรอก ISSN"}), 400

    try:
        result = fetch_scopus_metrics(
            issn,
            cookie_header=cookie_header,
            headless=headless,
        )
    except ScopusScraperError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502
    except Exception:  # pragma: no cover - defensive
        return jsonify({"success": False, "message": "ไม่สามารถดึงข้อมูลได้"}), 500

    return jsonify({"success": True, "data": result})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
