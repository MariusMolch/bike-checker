"""
Cube Agree C:62 Race – Verfügbarkeits-Checker
============================================
Läuft alle X Minuten, prüft Händlerverfügbarkeit per PLZ & Rahmengröße
und schickt eine HTML-Tabelle per E-Mail.
"""

import os
import shutil
import smtplib
import schedule
import time
import logging
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


def check_availability() -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results: list[tuple[str, list[dict]]] = []  # (groesse, stores)

    for groesse in RAHMENGROESSEN:
        log.info(f"Prüfe Verfügbarkeit für Größe {groesse} mit PLZ {PLZ} …")

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
                    page.wait_for_timeout(500)
                except Exception:
                    pass

                # Verfügbarkeits-Panel öffnen
                page.locator("#js_elio-store-locator-availability-link").click(timeout=10_000)
                form = page.locator("#js_store-locator-availability-form")
                form.wait_for(timeout=10_000)
                page.wait_for_timeout(500)

                # Rahmengröße auswählen
                groesse_label = groesse.replace("cm", " cm")
                try:
                    form.locator(".elio-custom-select-button.form-select").click(timeout=5_000)
                    page.wait_for_timeout(300)
                    form.locator(
                        f".elio-custom-select-option.form-select:has-text('{groesse_label}')"
                    ).click(timeout=5_000)
                    log.info(f"  Größe '{groesse_label}' ausgewählt")
                    page.wait_for_timeout(300)
                except Exception:
                    log.warning(f"  Größe '{groesse}' nicht auswählbar")

                # PLZ eingeben (Google Places Autocomplete)
                plz_input = page.locator("#js_store-locator-availability-input")
                plz_input.click(timeout=5_000)
                plz_input.fill(PLZ, timeout=5_000)
                page.wait_for_timeout(1_500)
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(300)
                page.keyboard.press("Enter")
                page.wait_for_timeout(3_000)

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

        except PWTimeout:
            log.error(f"  Timeout für Größe {groesse}")
        except Exception as exc:
            log.error(f"  Unerwarteter Fehler: {exc}", exc_info=True)

    if all_results:
        send_email(all_results)


def send_email(results: list[tuple[str, list[dict]]]) -> None:
    # Betreff: VERFÜGBAR wenn mindestens ein Laden avail==1, sonst Update
    verfuegbar_in = []
    for groesse, stores in results:
        for s in stores:
            if s["avail"] == "1":
                verfuegbar_in.append(f"{groesse} in {s['name']}")

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    if verfuegbar_in:
        subject = f"🚨🔥 Agree C:62 Race VERFÜGBAR – {', '.join(verfuegbar_in)} 🚨🔥"
    else:
        subject = f"Update {now_str}"

    # HTML-Body mit einer Tabelle pro Größe
    html_tables = "".join(build_html_table(g, s) for g, s in results)
    html_body = f"""
    <html><body style='font-family:sans-serif'>
      <h2>Cube Agree C:62 Race – Verfügbarkeits-Check</h2>
      <p>PLZ: {PLZ}<br>Zeitpunkt: {now_str}</p>
      {html_tables}
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["From"]    = ABSENDER_MAIL
    msg["To"]      = EMPFANGER_MAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(ABSENDER_MAIL, GMAIL_APP_PW)
            server.sendmail(ABSENDER_MAIL, EMPFANGER_MAIL, msg.as_string())
        log.info(f"  E-Mail gesendet: {subject}")
    except Exception as exc:
        log.error(f"  E-Mail-Versand fehlgeschlagen: {exc}")


def main():
    log.info("=== Cube Availability Checker gestartet ===")
    log.info(f"URL: {BIKE_URL}")
    log.info(f"PLZ: {PLZ}  |  Größen: {', '.join(RAHMENGROESSEN)}")
    log.info(f"Intervall: alle {INTERVALL_MIN} Minuten")

    check_availability()
    schedule.every(INTERVALL_MIN).minutes.do(check_availability)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
