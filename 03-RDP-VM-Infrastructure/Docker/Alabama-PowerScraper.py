"""
al_power_daily_importer.py

Alabama Power -> Home Assistant
Scrapes "Average Daily Usage" (kWh) from the My Power Usage page
and pushes it into a Home Assistant input_number.

Required environment variables:
- HA_URL
- HA_TOKEN
- INPUT_NUMBER_ENTITY
- AL_POWER_USERNAME
- AL_POWER_PASSWORD
- HEADLESS (optional: true/false)
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import requests
import json
import time
import os


# ========== CONFIG: HOME ASSISTANT ==========
HA_URL = os.getenv("HA_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
INPUT_NUMBER_ENTITY = os.getenv(
    "INPUT_NUMBER_ENTITY",
    "input_number.alabama_power_daily_kwh"
)

# ========== CONFIG: ALABAMA POWER LOGIN ==========
AL_POWER_USERNAME = os.getenv("AL_POWER_USERNAME", "")
AL_POWER_PASSWORD = os.getenv("AL_POWER_PASSWORD", "")

# ========== CONFIG: URLs / OPTIONS ==========
LOGIN_URL = (
    "https://customerlogin.southernco.com/am/XUI/"
    "?realm=/alpha&authIndexType=service&authIndexValue=occSecureLogin"
)
USAGE_URL = "https://customerservice2.southerncompany.com/Billing/MyPowerUsage?mnuOpco=APC"

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
DAILY_LABEL_TEXT = "Average Daily Usage"


def validate_config() -> None:
    """Ensure required configuration exists before running."""
    required = {
        "HA_TOKEN": HA_TOKEN,
        "AL_POWER_USERNAME": AL_POWER_USERNAME,
        "AL_POWER_PASSWORD": AL_POWER_PASSWORD,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )


# ---------------------------------------------------------
# Home Assistant helper
# ---------------------------------------------------------
def push_daily_kwh(kwh: float) -> None:
    """Send the daily kWh value into Home Assistant."""
    kwh = round(float(kwh), 3)

    url = f"{HA_URL}/api/services/input_number/set_value"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "entity_id": INPUT_NUMBER_ENTITY,
        "value": kwh,
    }

    print(f"[HA] Pushing {kwh} kWh to {INPUT_NUMBER_ENTITY} ...")
    resp = requests.post(url, headers=headers, data=json.dumps(data), timeout=15)
    print("[HA] Response:", resp.status_code, resp.text)
    resp.raise_for_status()


# ---------------------------------------------------------
# Scraping helper: login + daily kWh
# ---------------------------------------------------------
def scrape_daily_kwh() -> float:
    """Log into Alabama Power and scrape the 'Average Daily Usage' value (kWh)."""

    print("=== Alabama Power Daily Grid Importer ===")

    with sync_playwright() as p:
        print("[SCRAPE] Launching Chromium (headless =", HEADLESS, ")")
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        # 1) Go to login page
        print("[SCRAPE] Opening login page...")
        page.goto(LOGIN_URL, wait_until="networkidle")

        # 2) Fill username and password
        try:
            print("[SCRAPE] Waiting for username field...")
            username_input = page.wait_for_selector(
                'input[name="callback_1"], input[autocomplete="username"]',
                timeout=30000,
            )
        except PlaywrightTimeoutError as exc:
            browser.close()
            raise RuntimeError(
                "Timeout waiting for username field. Login page may have changed."
            ) from exc

        print("[SCRAPE] Waiting for password field...")
        try:
            password_input = page.wait_for_selector(
                'input[name="callback_2"], input[type="password"]',
                timeout=30000,
            )
        except PlaywrightTimeoutError as exc:
            browser.close()
            raise RuntimeError(
                "Timeout waiting for password field. Login page may have changed."
            ) from exc

        print("[SCRAPE] Filling username/password...")
        username_input.fill(AL_POWER_USERNAME)
        password_input.fill(AL_POWER_PASSWORD)

        # 3) Click Log In button
        print("[SCRAPE] Locating login button...")
        login_button = page.query_selector(
            'button[data-testid="btn-login"], button[type="submit"]'
        )
        if not login_button:
            browser.close()
            raise RuntimeError("Could not find login button on login page.")

        print("[SCRAPE] Clicking login button...")
        login_button.click()

        print("[SCRAPE] Waiting for login network to settle...")
        page.wait_for_load_state("networkidle")

        # 4) Navigate to My Power Usage page
        print("[SCRAPE] Navigating to My Power Usage page...")
        page.goto(USAGE_URL, wait_until="networkidle")

        time.sleep(5)

        # 5) Locate the correct iframe dynamically
        print("[SCRAPE] Locating usage iframe...")

        target_frame = None

        for frame in page.frames:
            if "MyPowerUsage" in (frame.url or ""):
                target_frame = frame
                break

        if not target_frame:
            print("[SCRAPE] Could not find frame by URL; trying generic <iframe> search.")
            frame_elements = page.locator("iframe")
            count = frame_elements.count()
            for i in range(count):
                candidate = frame_elements.nth(i).content_frame()
                if candidate and candidate.url:
                    print(f"[SCRAPE] Considering iframe #{i} with URL: {candidate.url}")
                    target_frame = candidate
                    break

        if not target_frame:
            browser.close()
            raise RuntimeError("Could not locate the Alabama Power usage iframe.")

        iframe = target_frame
        print("[SCRAPE] Using iframe with URL:", iframe.url)

        # 6) Make sure DAILY tab is active
        try:
            print("[SCRAPE] Waiting for DAILY tab inside iframe...")
            daily_tab = iframe.wait_for_selector(
                'label[name="resolutionDaily"], label:has-text("DAILY")',
                timeout=30000,
            )
            print("[SCRAPE] Clicking DAILY tab (if not already active)...")
            daily_tab.click()
            time.sleep(3)
        except PlaywrightTimeoutError:
            print("[SCRAPE] DAILY tab not found; assuming already in daily view.")

        # 7) Find the Average Daily Usage card
        try:
            print(f"[SCRAPE] Looking for '{DAILY_LABEL_TEXT}' card title inside iframe...")
            title_el = iframe.wait_for_selector(
                f"h3.insights-title:has-text('{DAILY_LABEL_TEXT}')",
                timeout=60000,
            )
        except PlaywrightTimeoutError as exc:
            browser.close()
            raise RuntimeError(
                "Timed out waiting for the 'Average Daily Usage' card. "
                "Check that the page layout or text hasn't changed."
            ) from exc

        card_body = title_el.locator("xpath=..")
        description_el = card_body.locator("div.insights-description")

        text = description_el.inner_text().strip()
        browser.close()

    # 8) Clean text into a float
    cleaned = (
        text.replace("kWh", "")
        .replace("kW h", "")
        .replace(",", "")
        .strip()
    )

    print("[SCRAPE] Raw text from card:", repr(text))
    print("[SCRAPE] Cleaned numeric part:", repr(cleaned))

    try:
        value = float(cleaned)
    except ValueError as exc:
        raise RuntimeError(f"Could not convert '{cleaned}' to float") from exc

    print(f"[SCRAPE] Final daily kWh value: {value}")
    return value


def main() -> None:
    validate_config()

    try:
        daily_kwh = scrape_daily_kwh()
    except Exception as exc:
        print("[ERROR] While scraping Alabama Power:", repr(exc))
        return

    try:
        push_daily_kwh(daily_kwh)
    except Exception as exc:
        print("[ERROR] While pushing to Home Assistant:", repr(exc))
        return

    print("=== Done: Alabama Power daily kWh imported into Home Assistant ===")


if __name__ == "__main__":
    main()
