import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

PRODUCTS_FILE = Path("products.json")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# We search representative NZ locations so the Stockinstore widget returns
# actual store cards. This avoids treating the generic "1 Hour Click & Collect
# Available" banner as store stock.
SEARCH_LOCATIONS = [
    ("Northland", "Whangarei"),
    ("Auckland", "Auckland"),
    ("Waikato", "Hamilton"),
    ("Bay of Plenty", "Tauranga"),
    ("Gisborne", "Gisborne"),
    ("Hawke's Bay", "Napier"),
    ("Taranaki", "New Plymouth"),
    ("Manawatu-Whanganui", "Palmerston North"),
    ("Wellington", "Wellington"),
    ("Nelson-Tasman", "Nelson"),
    ("Marlborough", "Blenheim"),
    ("Canterbury", "Christchurch"),
    ("Otago", "Dunedin"),
    ("Southland", "Invercargill"),
]

GENERIC_PHRASES = {
    "1 hour click & collect available",
    "1 hour click & collect",
    "find your local store",
    "skip to content",
    "gift cards",
    "search",
    "clear",
}

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    import requests
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": True},
        timeout=20,
    )

def load_products():
    with PRODUCTS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def toyworld_products():
    return [p for p in load_products() if p.get("retailer") == "Toyworld NZ"]

def clean_lines(text):
    return [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]

def status_of(line):
    u = line.upper()
    if "CALL TO CONFIRM" in u:
        return "CALL TO CONFIRM"
    # Only treat a standalone AVAILABLE result as store stock. The generic
    # click-and-collect banner is explicitly excluded.
    if re.search(r"\bAVAILABLE\b", u) and "CLICK & COLLECT" not in u:
        return "AVAILABLE"
    if "OUT OF STOCK" in u:
        return "OUT OF STOCK"
    return None

def is_generic(line):
    return line.lower().strip(" |") in GENERIC_PHRASES

def find_store_cards(lines):
    """Return (store_name, status) pairs from rendered Stockinstore cards.

    We require a plausible store-name line near a status line. A bare
    'AVAILABLE' line is never considered enough.
    """
    results = []
    # Common Toyworld naming convention plus a conservative fallback for
    # lines containing a city/town and the word Toyworld.
    for i, line in enumerate(lines):
        status = status_of(line)
        if not status or is_generic(line):
            continue

        window = lines[max(0, i-7):i+1]
        candidate = None
        for prev in reversed(window[:-1]):
            low = prev.lower()
            if is_generic(prev):
                continue
            if "toyworld" in low and len(prev) < 100:
                candidate = prev
                break
            # A store card may show a plain store name followed by address.
            if any(x in low for x in (
                "whangarei","auckland","albany","hamilton","tauranga",
                "rotorua","gisborne","napier","hastings","new plymouth",
                "palmerston north","whanganui","wellington","porirua",
                "lower hutt","upper hutt","nelson","richmond","blenheim",
                "christchurch","ashburton","timaru","dunedin","queenstown",
                "invercargill","gore"
            )) and len(prev) < 100:
                candidate = prev
                break

        if candidate:
            results.append((candidate, status))
    # de-duplicate
    return list(dict.fromkeys(results))

def search_location(page, location):
    """Use the visible store-finder control when available."""
    # Click the first visible control containing 'Find Your Local Store'.
    buttons = page.get_by_text("Find Your Local Store", exact=True)
    if buttons.count():
        try:
            buttons.first.click(timeout=3000)
            page.wait_for_timeout(500)
        except Exception:
            pass

    # Find a visible text/search input associated with the store finder.
    inputs = page.locator("input:visible")
    for i in range(inputs.count()):
        el = inputs.nth(i)
        try:
            ph = (el.get_attribute("placeholder") or "").lower()
            aria = (el.get_attribute("aria-label") or "").lower()
            name = (el.get_attribute("name") or "").lower()
            if any(k in (ph + " " + aria + " " + name)
                   for k in ("store", "location", "postcode", "suburb", "search")):
                el.fill(location)
                el.press("Enter")
                page.wait_for_timeout(2500)
                return True
        except Exception:
            continue
    return False

def main():
    products = toyworld_products()
    if not products:
        print("No Toyworld products in products.json")
        return

    alerts = []
    checked_pairs = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/140.0.0.0 Safari/537.36",
        )

        for product in products:
            print(f"\nChecking: {product['name']}")
            for region, location in SEARCH_LOCATIONS:
                try:
                    page.goto(product["url"], wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(3500)
                    search_location(page, location)
                    page.wait_for_timeout(2000)

                    lines = clean_lines(page.locator("body").inner_text(timeout=15000))
                    cards = find_store_cards(lines)

                    for store, status in cards:
                        key = (product["name"], store, status)
                        if key in checked_pairs:
                            continue
                        checked_pairs.add(key)
                        print(f"  {region} | {store} | {status}")

                        if status in ("AVAILABLE", "CALL TO CONFIRM"):
                            alerts.append(
                                f"🚨 TOYWORLD IN-STORE STOCK\n"
                                f"{product['name']}\n"
                                f"📍 {region} | {store}\n"
                                f"📦 {status}\n"
                                f"🛒 {product['url']}"
                            )
                except Exception as e:
                    print(f"  {region}: ERROR {e}")

        browser.close()

    print("\n=== TOYWORLD REGIONAL SUMMARY ===")
    print(f"Products checked: {len(products)}")
    print(f"Store-stock positives: {len(alerts)}")
    if alerts:
        # Group into one Telegram message, avoiding spam.
        send_telegram("\n\n".join(alerts)[:3900])
    else:
        print("No confirmed store-level AVAILABLE/CALL TO CONFIRM results found.")

if __name__ == "__main__":
    main()
