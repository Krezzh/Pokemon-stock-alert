import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

PRODUCTS_FILE = Path("products.json")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Only check Manawatu and the lower North Island
SEARCH_LOCATIONS = [
    ("Manawatu-Whanganui", "Palmerston North"),
    ("Manawatu-Whanganui", "Whanganui"),
    ("Horowhenua", "Levin"),
    ("Wellington", "Wellington"),
    ("Wairarapa", "Masterton"),
    ("Taranaki", "New Plymouth"),
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

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram error: {e}")


def load_products():
    with PRODUCTS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def toyworld_products():
    return [
        p for p in load_products()
        if p.get("retailer") == "Toyworld NZ"
    ]


def clean_lines(text):
    return [
        re.sub(r"\s+", " ", x).strip()
        for x in text.splitlines()
        if x.strip()
    ]


def status_of(line):
    u = line.upper()

    if "CALL TO CONFIRM" in u:
        return "CALL TO CONFIRM"

    if re.search(r"\bAVAILABLE\b", u) and "CLICK & COLLECT" not in u:
        return "AVAILABLE"

    if "OUT OF STOCK" in u:
        return "OUT OF STOCK"

    return None


def is_generic(line):
    return line.lower().strip(" |") in GENERIC_PHRASES


def find_store_cards(lines):
    results = []

    for i, line in enumerate(lines):
        status = status_of(line)

        if not status or is_generic(line):
            continue

        window = lines[max(0, i - 7):i + 1]
        candidate = None

        for prev in reversed(window[:-1]):
            low = prev.lower()

            if is_generic(prev):
                continue

            if "toyworld" in low and len(prev) < 100:
                candidate = prev
                break

            if any(x in low for x in (
                "palmerston north",
                "whanganui",
                "levin",
                "wellington",
                "masterton",
                "new plymouth",
                "manawatu",
                "horowhenua",
                "wairarapa",
                "taranaki",
            )) and len(prev) < 100:
                candidate = prev
                break

        if candidate:
            results.append((candidate, status))

    return list(dict.fromkeys(results))


def search_location(page, location):
    try:
        buttons = page.get_by_text(
            "Find in Store",
            exact=True
        )

        if buttons.count():
            try:
                buttons.first.click(timeout=2000)
                page.wait_for_timeout(300)
            except Exception:
                pass

        inputs = page.locator("input:visible")

        for i in range(inputs.count()):
            el = inputs.nth(i)

            try:
                ph = (el.get_attribute("placeholder") or "").lower()
                aria = (el.get_attribute("aria-label") or "").lower()
                name = (el.get_attribute("name") or "").lower()

                info = ph + " " + aria + " " + name

                if any(k in info for k in (
                    "store",
                    "location",
                    "postcode",
                    "suburb",
                    "search"
                )):
                    el.fill(location, timeout=2000)
                    el.press("Enter", timeout=2000)

                    page.wait_for_timeout(1200)
                    return True

            except Exception:
                continue

    except Exception as e:
        print(f"    Search error: {e}")

    return False


def main():
    products = toyworld_products()

    if not products:
        print("No Toyworld products in products.json")
        return

    alerts = []
    checked_pairs = set()

    print(f"Toyworld products found: {len(products)}")
    print(f"Regions to check: {len(SEARCH_LOCATIONS)}")

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1200
            },
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
        )

        for product in products:

            print("\n==============================")
            print(f"Checking: {product['name']}")
            print("==============================")

            try:
                page.goto(
                    product["url"],
                    wait_until="domcontentloaded",
                    timeout=20000
                )

                page.wait_for_timeout(2000)

            except Exception as e:
                print(f"  Product page failed: {e}")
                continue

            for region, location in SEARCH_LOCATIONS:

                print(
                    f"  Checking {region} "
                    f"({location})..."
                )

                try:
                    found = search_location(
                        page,
                        location
                    )

                    if not found:
                        print(
                            "    Store search box not found"
                        )
                        continue

                    try:
                        body = page.locator(
                            "body"
                        ).inner_text(timeout=5000)

                        lines = clean_lines(body)
                        cards = find_store_cards(lines)

                    except Exception as e:
                        print(
                            f"    Could not read results: {e}"
                        )
                        continue

                    for store, status in cards:

                        key = (
                            product["name"],
                            store,
                            status
                        )

                        if key in checked_pairs:
                            continue

                        checked_pairs.add(key)

                        print(
                            f"    {region} | "
                            f"{store} | "
                            f"{status}"
                        )

                        if status in (
                            "AVAILABLE",
                            "CALL TO CONFIRM"
                        ):
                            alerts.append(
                                "🚨 TOYWORLD IN-STORE STOCK\n"
                                f"{product['name']}\n"
                                f"📍 {region} | {store}\n"
                                f"📦 {status}\n"
                                f"🛒 {product['url']}"
                            )

                except Exception as e:
                    print(
                        f"    {region}: ERROR {e}"
                    )

        browser.close()

    print("\n==============================")
    print("TOYWORLD REGIONAL SUMMARY")
    print("==============================")
    print(
        f"Products checked: {len(products)}"
    )
    print(
        f"Store-stock positives: {len(alerts)}"
    )

    if alerts:
        send_telegram(
            "\n\n".join(alerts)[:3900]
        )
    else:
        print(
            "No confirmed store-level "
            "AVAILABLE/CALL TO CONFIRM "
            "results found."
        )


if __name__ == "__main__":
    main()
