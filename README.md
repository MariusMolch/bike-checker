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
   ```

2. Install Chromium:

   **Linux / macOS / Windows** — Playwright's bundled Chromium:
   ```bash
   playwright install chromium
   playwright install-deps chromium
   ```

   **Raspberry Pi (ARM)** — System Chromium (Playwright's bundled binary doesn't support ARM):
   ```bash
   sudo apt update && sudo apt install -y chromium
   ```
   The script auto-detects `/usr/bin/chromium` and `/usr/bin/chromium-browser` and uses whichever is present. No extra config needed.

3. Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```

4. Run:
   ```bash
   python main.py
   ```

### Run as a systemd service (Raspberry Pi)

To start the checker automatically on boot:

```bash
sudo nano /etc/systemd/system/bike-checker.service
```

```ini
[Unit]
Description=Cube Bike Checker
After=network.target

[Service]
WorkingDirectory=/home/pi/bike-checker
ExecStart=/home/pi/bike-checker/.venv/bin/python main.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now bike-checker
# Check logs:
journalctl -u bike-checker -f
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
