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
WorkingDirectory=/home/<your-user>/bike-checker
ExecStart=/home/<your-user>/bike-checker/.venv/bin/python main.py
Restart=always
User=<your-user>

[Install]
WantedBy=multi-user.target
```

Replace `<your-user>` with your actual username (e.g. `pi` or whatever `whoami` returns).

```bash
sudo systemctl enable --now bike-checker
```

Useful commands:
```bash
sudo systemctl status bike-checker   # check if running
sudo systemctl stop bike-checker     # stop the service
sudo systemctl restart bike-checker  # restart (e.g. after git pull)
journalctl -u bike-checker -f        # live logs
```

> `Restart=always` means systemd will automatically restart the script if it crashes or is killed. To permanently stop it, use `systemctl stop`.

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
