"""
Cube Agree C:62 Race – Verfügbarkeits-Checker
============================================
Läuft alle X Minuten, prüft Händlerverfügbarkeit per PLZ & Rahmengröße
und schickt eine HTML-Tabelle per E-Mail.
"""

import os
import json
import shutil
import smtplib
import threading
import schedule
import time
import logging
import requests
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv()

BIKE_URL       = os.environ["BIKE_URL"]
PLZ            = os.environ["PLZ"]
RAHMENGROESSEN = [g.strip() for g in os.environ["RAHMENGROESSEN"].split(",")]

SMTP_HOST      = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.environ.get("SMTP_PORT", "587"))
ABSENDER_MAIL  = os.environ["ABSENDER_MAIL"]
EMPFANGER_MAIL = os.environ["EMPFANGER_MAIL"]
GMAIL_APP_PW   = os.environ["GMAIL_APP_PW"]

INTERVALL_MIN  = int(os.environ.get("INTERVALL_MIN", "30"))
SCREENSHOT_DIR = Path("screenshots")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")

_CHROMIUM_CANDIDATES = ["/usr/bin/chromium", "/usr/bin/chromium-browser"]
CHROMIUM_PATH = next((p for p in _CHROMIUM_CANDIDATES if shutil.which(p)), None)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("cube_checker.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)
SCREENSHOT_DIR.mkdir(exist_ok=True)

AVAILABILITY_LABEL = {
    "1": "✅ Verfügbar",
    "2": "🟡 Demnächst verfügbar",
    "3": "🟠 Bald erhältlich",
}


def scrape_stores(page) -> list[dict]:
    """Liest alle Shop-Einträge aus dem geladenen Panel."""
    stores = []
    entries = page.locator(".js_store-locator-store.store-locator__store-entry").all()
    for entry in entries:
        name       = (entry.get_attribute("data-name") or "").strip()
        avail_code = (entry.get_attribute("data-availability") or "").strip()
        city       = (entry.get_attribute("data-city") or "").strip()
        dist_el    = entry.locator(".store-locator__store-entry-distance")
        distance   = dist_el.inner_text().strip().split("\n")[0].strip() if dist_el.count() else "–"
        stores.append({
            "name":      name,
            "city":      city,
            "avail":     avail_code,
            "avail_txt": AVAILABILITY_LABEL.get(avail_code, avail_code),
            "distance":  distance,
        })
    return stores


def build_html_table(groesse: str, stores: list[dict]) -> str:
    rows = ""
    for s in stores:
        bg = "#d4edda" if s["avail"] == "1" else "#fff3cd" if s["avail"] == "2" else "#fde8d0"
        rows += (
            f"<tr style='background:{bg}'>"
            f"<td style='padding:6px 10px'>{s['name']}</td>"
            f"<td style='padding:6px 10px'>{s['city']}</td>"
            f"<td style='padding:6px 10px'>{s['avail_txt']}</td>"
            f"<td style='padding:6px 10px;text-align:right'>{s['distance']}</td>"
            f"</tr>"
        )
    return f"""
    <h3 style='font-family:sans-serif'>Rahmengröße {groesse} – {datetime.now().strftime('%d.%m.%Y %H:%M')}</h3>
    <table style='border-collapse:collapse;font-family:sans-serif;font-size:14px;width:100%'>
      <thead>
        <tr style='background:#333;color:#fff'>
          <th style='padding:8px 10px;text-align:left'>Laden</th>
          <th style='padding:8px 10px;text-align:left'>Stadt</th>
          <th style='padding:8px 10px;text-align:left'>Verfügbarkeit</th>
          <th style='padding:8px 10px;text-align:right'>Entfernung</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    """


def run_check() -> list[tuple[str, list[dict]]]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results: list[tuple[str, list[dict]]] = []

    for groesse in RAHMENGROESSEN:
        for versuch in range(1, 3):
            log.info(f"Prüfe Verfügbarkeit für Größe {groesse} mit PLZ {PLZ} … (Versuch {versuch}/2)")
            try:
                with sync_playwright() as p:
                    launch_args = {"headless": True}
                    if CHROMIUM_PATH:
                        launch_args["executable_path"] = CHROMIUM_PATH
                    browser = p.chromium.launch(**launch_args)
                    page = browser.new_page(
                        viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    )

                    page.goto(BIKE_URL, wait_until="domcontentloaded", timeout=30_000)

                    # Cookie-Banner wegklicken
                    try:
                        page.locator("button:has-text('Akzeptieren'), button:has-text('Alle akzeptieren')").first.click(timeout=8_000)
                        page.wait_for_timeout(1_000)
                    except Exception:
                        pass

                    # Verfügbarkeits-Panel öffnen
                    page.locator("#js_elio-store-locator-availability-link").click(timeout=10_000)
                    form = page.locator("#js_store-locator-availability-form")
                    form.wait_for(timeout=10_000)
                    page.wait_for_timeout(1_000)

                    # Rahmengröße auswählen
                    groesse_label = groesse.replace("cm", " cm")
                    try:
                        form.locator(".elio-custom-select-button.form-select").click(timeout=5_000)
                        page.wait_for_timeout(800)
                        form.locator(
                            f".elio-custom-select-option.form-select:has-text('{groesse_label}')"
                        ).click(timeout=5_000)
                        log.info(f"  Größe '{groesse_label}' ausgewählt")
                        page.wait_for_timeout(800)
                    except Exception:
                        log.warning(f"  Größe '{groesse}' nicht auswählbar")

                    # PLZ eingeben (Google Places Autocomplete)
                    plz_input = page.locator("#js_store-locator-availability-input")
                    plz_input.click(timeout=5_000)
                    plz_input.fill(PLZ, timeout=5_000)
                    page.wait_for_timeout(3_000)
                    page.keyboard.press("ArrowDown")
                    page.wait_for_timeout(800)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(4_000)

                    # Stores scrapen
                    stores = scrape_stores(page)
                    log.info(f"  {len(stores)} Läden gefunden")
                    for s in stores:
                        log.info(f"    {s['name']} ({s['distance']}) – {s['avail_txt']}")

                    # Screenshot
                    screenshot_path = SCREENSHOT_DIR / f"cube_{groesse}_{ts}.png"
                    page.screenshot(path=str(screenshot_path), full_page=False)
                    browser.close()

                all_results.append((groesse, stores))
                break

            except PWTimeout:
                log.warning(f"  Timeout für Größe {groesse} (Versuch {versuch}/2)")
                if versuch == 2:
                    log.error(f"  Größe {groesse} nach 2 Versuchen übersprungen")
                else:
                    time.sleep(5)
            except Exception as exc:
                log.error(f"  Unerwarteter Fehler: {exc}", exc_info=True)
                break

    return all_results


def check_availability() -> None:
    if datetime.now().hour < 8:
        log.info("Außerhalb der Prüfzeit (0–8 Uhr), überspringe.")
        return
    results = run_check()
    if results:
        has_available = any(s["avail"] == "1" for _, stores in results for s in stores)
        if has_available:
            send_email(results)


def send_daily_summary() -> None:
    log.info("=== Tagesabschluss 20 Uhr ===")
    results = run_check()
    if results:
        send_email(results, daily_summary=True)


def send_email(results: list[tuple[str, list[dict]]], daily_summary: bool = False) -> None:
    verfuegbar_in = [
        f"{groesse} in {s['name']}"
        for groesse, stores in results
        for s in stores
        if s["avail"] == "1"
    ]

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    if daily_summary:
        subject = f"Tagesabschluss {now_str} – {'VERFÜGBAR: ' + ', '.join(verfuegbar_in) if verfuegbar_in else 'nichts verfügbar'}"
    else:
        subject = f"🚨🔥 Agree C:62 Race VERFÜGBAR – {', '.join(verfuegbar_in)} 🚨🔥"

    html_tables = "".join(build_html_table(g, s) for g, s in results)
    html_body = f"""
    <html><body style='font-family:sans-serif'>
      <h2>Cube Agree C:62 Race – Verfügbarkeits-Check</h2>
      <p>PLZ: {PLZ}<br>Zeitpunkt: {now_str}</p>
      {html_tables}
    </body></html>
    """

    msg = MIMEMultipart("mixed")
    msg["From"]    = ABSENDER_MAIL
    msg["To"]      = EMPFANGER_MAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if daily_summary and Path("cube_checker.log").exists():
        with open("cube_checker.log", "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename="cube_checker.log")
        msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(ABSENDER_MAIL, GMAIL_APP_PW)
            server.sendmail(ABSENDER_MAIL, EMPFANGER_MAIL, msg.as_string())
        log.info(f"  E-Mail gesendet: {subject}")
    except Exception as exc:
        log.error(f"  E-Mail-Versand fehlgeschlagen: {exc}")


def ntfy_publish(message: str, title: str = "Bike Checker") -> None:
    if not NTFY_TOPIC or not NTFY_TOKEN:
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Authorization": f"Bearer {NTFY_TOKEN}", "Title": title, "Tags": "from-script"},
            timeout=10,
        )
    except Exception as exc:
        log.error(f"ntfy publish fehlgeschlagen: {exc}")


_check_lock = threading.Lock()

def on_demand_check() -> None:
    if not _check_lock.acquire(blocking=False):
        log.info("Prüfung läuft bereits, Trigger ignoriert.")
        ntfy_publish("Prüfung läuft bereits, bitte kurz warten.", title="Bike Checker")
        return
    try:
        log.info("=== On-Demand Prüfung (ntfy Trigger) ===")
        ntfy_publish("Prüfung gestartet…", title="Bike Checker")
        results = run_check()
        if not results:
            ntfy_publish("Prüfung fehlgeschlagen.", title="Bike Checker Fehler")
            return
        send_email(results, daily_summary=True)
        has_available = any(s["avail"] == "1" for _, stores in results for s in stores)
        if has_available:
            verfuegbar = [f"{g}: {s['name']}" for g, stores in results for s in stores if s["avail"] == "1"]
            ntfy_publish("🚨 VERFÜGBAR: " + ", ".join(verfuegbar), title="Bike verfügbar!")
        else:
            ntfy_publish("Kein Bike verfügbar. Mail mit Details gesendet.", title="Bike Checker")
    finally:
        _check_lock.release()


def ntfy_listener() -> None:
    if not NTFY_TOPIC or not NTFY_TOKEN:
        return
    log.info(f"ntfy Listener gestartet (Topic: {NTFY_TOPIC})")
    while True:
        try:
            with requests.get(
                f"https://ntfy.sh/{NTFY_TOPIC}/json",
                headers={"Authorization": f"Bearer {NTFY_TOKEN}"},
                stream=True,
                timeout=None,
            ) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get("event") == "message":
                        if "from-script" in (msg.get("tags") or []):
                            continue
                        log.info(f"ntfy Trigger empfangen: {msg.get('message', '')}")
                        threading.Thread(target=on_demand_check, daemon=True).start()
        except Exception as exc:
            log.error(f"ntfy Listener Fehler: {exc} – Neuverbindung in 30s")
            time.sleep(30)


def main():
    log.info("=== Cube Availability Checker gestartet ===")
    log.info(f"URL: {BIKE_URL}")
    log.info(f"PLZ: {PLZ}  |  Größen: {', '.join(RAHMENGROESSEN)}")
    log.info(f"Intervall: alle {INTERVALL_MIN} Minuten")

    threading.Thread(target=ntfy_listener, daemon=True).start()

    check_availability()
    schedule.every(INTERVALL_MIN).minutes.do(check_availability)
    schedule.every().day.at("12:00").do(send_daily_summary)
    schedule.every().day.at("20:00").do(send_daily_summary)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
