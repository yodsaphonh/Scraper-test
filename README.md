# Scopus Metrics Web Scraper

A Flask-based web application that automates the Scopus search workflow for a given ISSN using Playwright. The UI submits the ISSN to Scopus, collects CiteScore, SJR, SNIP, and quartile details, and presents the metrics in a responsive dark-themed interface with a light/dark theme toggle.

## Features

- Web UI for entering an ISSN and triggering the scraper.
- Playwright automation to perform the Scopus search and parse the results.
- Displays CiteScore, SJR, SNIP, and subject area quartiles (Q1-Q4).
- Dark theme by default with a client-side toggle to switch to a light theme.
- Optional cookie/header configuration for authenticated Scopus sessions.

## Prerequisites

- Python 3.9 or later (Playwright recommends 3.8+).
- Google Chrome, Microsoft Edge, or another Chromium-based browser if you plan to run Playwright headed (headless is supported out of the box).
- Scopus access that matches your institution's subscription. Some results may require an authenticated session via cookies.

## Installation

1. **Clone the repository and enter the project directory**

   ```bash
   git clone <repository-url>
   cd Scraper-test
   ```

2. **Create a virtual environment (recommended)**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

3. **Install Python dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browser drivers**

   ```bash
   python -m playwright install
   ```

## Configuration

Environment variables can be placed in a `.env` file at the project root or exported in your shell before starting the app.

- `SCOPUS_COOKIE` – Optional cookie header string used for authenticated Scopus sessions.
- `SCOPUS_HEADLESS` – Set to `false` (case-insensitive) to launch the Playwright browser in headed mode. Defaults to `true` (headless).
- `PORT` – Optional port override for the Flask development server. Defaults to `8000`.

Example `.env` file:

```env
SCOPUS_COOKIE=_scopus_session=...; other_cookie=value
SCOPUS_HEADLESS=true
PORT=8000
```

## Running the Application

Start the Flask server directly with Python:

```bash
python app.py
```

The server listens on `http://127.0.0.1:8000` by default. If you override `PORT`, open the corresponding URL in your browser.

## Using the Web UI

1. Open the application in your browser.
2. Enter the ISSN you want to look up.
3. (Optional) Provide a cookie header string if your Scopus access requires authentication.
4. Choose whether to run the browser headless.
5. Click **ค้นหา** to start the scrape.
6. Wait for the loader to finish. Results will appear in cards showing CiteScore, SJR, SNIP, and quartile classifications by subject area.
7. Use the theme toggle button in the header to switch between dark and light themes.

## API Endpoint

The same functionality is available through a JSON API:

- **Endpoint:** `POST /api/scrape`
- **Payload:**

  ```json
  {
    "issn": "1234-5678",
    "cookie": "optional cookie header",
    "headless": true
  }
  ```

- **Response:**

  ```json
  {
    "success": true,
    "data": {
      "issn": "1234-5678",
      "citescore": "12.3",
      "sjr": "0.456",
      "snip": "1.23",
      "quartiles": [
        {
          "subject_area": "Computer Science",
          "quartile": "Q1"
        }
      ]
    }
  }
  ```

Unsuccessful responses include `success: false` and a `message` explaining the issue.

## Troubleshooting

- **Playwright cannot launch the browser** – Ensure `python -m playwright install` completed successfully and that the underlying browser dependencies (such as libatk, libnss3, etc.) are available on your OS.
- **Scopus returns limited data or prompts for login** – Provide a valid `SCOPUS_COOKIE` value from an authenticated browser session.
- **Headed mode fails inside containers/servers** – Leave `SCOPUS_HEADLESS` at its default (`true`) or set up a virtual display (e.g., Xvfb) if headed mode is required.

## Development Notes

- The project uses Flask's built-in development server. For production deployments, run the app with a production-grade WSGI server (e.g., Gunicorn) and configure HTTPS.
- Static assets live under `static/`, and Jinja2 templates live under `templates/`.
- The scraper logic is encapsulated in `scraper.py`; `app.py` wires it into the web interface and API.

## License

This project is provided as-is without an explicit license. Add licensing information here if needed.
