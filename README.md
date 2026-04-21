# Cube Bike Availability Checker

Checks availability of a Cube bike at local dealers and sends an email notification with a table of stores, availability status and distance.

## Setup

1. Clone the repo and create a virtual environment:
   ```bash
   git clone https://github.com/MariusMolch/bike-checker
   cd bike-checker
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   playwright install-deps chromium
   ```

2. Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```

3. Run:
   ```bash
   python main.py
   ```

## Configuration (`.env`)

| Variable | Description |
|---|---|
| `BIKE_URL` | Product page URL on cube.eu |
| `PLZ` | Your location, e.g. `12345 Meine Stadt, Deutschland` |
| `RAHMENGROESSEN` | Comma-separated sizes, e.g. `56cm,58cm` |
| `ABSENDER_MAIL` | Gmail address to send from |
| `EMPFANGER_MAIL` | Email address to notify |
| `GMAIL_APP_PW` | Gmail App Password (not your regular password) |
| `INTERVALL_MIN` | Check interval in minutes |

## Email

Each email contains an HTML table with store name, city, availability and distance.
