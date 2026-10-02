import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

PRODUCTS_FILE = Path("products.json")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Only check Toyworld Palmerston North
SEARCH_LOCATIONS = [
    ("Manawatu-Whanganui", "Palmerston North"),
]

# TCG-related words.
# This catches products even if the product name does not literally
# contain the letters "TCG".
TCG_KEYWORDS = (
    "tcg",
    "booster",
    "elite trainer",
    "etb",
    "blister",
    "booster bundle",
    "booster box",
    "trading card",
    "trading cards",
    "pokemon cards",
    "pokemon card",
    "deck",
)

GENERIC_PHRASES = {
    "1 hour click & collect available",
    "1 hour click & collect",
    "find your local store",
    "find in store",
    "edit search",
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
    products = []

    for product in load_products():

        if product.get("retailer") != "Toyworld NZ":
            continue

        name = product.get("name", "").lower()

        # Only keep TCG/card products.
        if any(keyword in name for keyword in TCG_KEYWORDS):
            products.append(product)

    return products


def clean_lines(text):
    return [
        re.sub(r"\s+", " ", x).strip()
        for x in text.splitlines()
        if x.strip()
    ]


def status_of(line):
    u = line.upper()

    # Toyworld's actual store wording
    if "FIND IN-STORE" in u and "AVAILABLE" in u:
        return "AVAILABLE"

    if "FIND IN STORE" in u and "AVAILABLE" in u:
        return "AVAILABLE"

    if "CALL TO CONFIRM" in u:
        return "CALL TO CONFIRM"

    if "OUT OF STOCK" in u:
        return "OUT OF STOCK"

    # General fallback
    if re.search(r"\bAVAILABLE\b", u):
        if "CLICK & COLLECT" not in u:
            return "AVAILABLE"

    return None


def is_generic(line):
    return line.lower().strip(" |") in GENERIC_PHRASES


def find_store_cards(lines):
    results = []

    for i, line in enumerate(lines):

        status = status_of(line)

        if not status or is_generic(line):
            continue

        # Look backwards for the store name.
        window = lines[max(0, i - 10):i + 1]

        candidate = None

        for prev in reversed(window[:-1]):

            low = prev.lower()

            if is_generic(prev):
                continue

            # Normal Toyworld store name
            if "toyworld" in low and len(prev) < 120:
                candidate = prev
                break

            # Palmerston North fallback
            if (
                "palmerston north" in low
                and len(prev) < 120
            ):
                candidate = prev
                break

        if candidate:
            results.append(
                (candidate, status)
            )

    return list(dict.fromkeys(results))


def search_location(page, location):

    try:
        # -------------------------------------------------
        # 1. Open "Find in Store"
        # -------------------------------------------------

        buttons = page.get_by_text(
            "Find in Store",
            exact=True
        )

        if buttons.count():

            try:
                buttons.first.click(
                    timeout=3000
                )

                page.wait_for_timeout(1000)

            except Exception as e:
                print(
                    f"    Could not open "
                    f"Find in Store: {e}"
                )

        else:
            print(
                "    Find in Store button "
                "not found"
            )
            return False

        # -------------------------------------------------
        # 2. Click "Edit Search"
        # -------------------------------------------------

        edit_search = page.get_by_text(
            "Edit Search",
            exact=True
        )

        if edit_search.count():

            try:
                edit_search.first.click(
                    timeout=3000
                )

                page.wait_for_timeout(500)

            except Exception as e:
                print(
                    f"    Could not click "
                    f"Edit Search: {e}"
                )

        # -------------------------------------------------
        # 3. Find the location search input
        # -------------------------------------------------

        inputs = page.locator(
            "input:visible"
        )

        for i in range(inputs.count()):

            el = inputs.nth(i)

            try:

                placeholder = (
                    el.get_attribute(
                        "placeholder"
                    ) or ""
                ).lower()

                aria = (
                    el.get_attribute(
                        "aria-label"
                    ) or ""
                ).lower()

                name = (
                    el.get_attribute(
                        "name"
                    ) or ""
                ).lower()

                input_type = (
                    el.get_attribute(
                        "type"
                    ) or ""
                ).lower()

                info = (
                    placeholder
                    + " "
                    + aria
                    + " "
                    + name
                    + " "
                    + input_type
                )

                if any(keyword in info for keyword in (
                    "store",
                    "location",
                    "postcode",
                    "post code",
                    "suburb",
                    "search",
                )):

                    el.fill(
                        location,
                        timeout=3000
                    )

                    el.press(
                        "Enter",
                        timeout=3000
                    )

                    page.wait_for_timeout(
                        1500
                    )

                    return True

            except Exception:
                continue

        # -------------------------------------------------
        # 4. Fallback: try visible text inputs
        # -------------------------------------------------

        text_inputs = page.locator(
            "input[type='text']:visible"
        )

        if text_inputs.count():

            try:

                el = text_inputs.first

                el.fill(
                    location,
                    timeout=3000
                )

                el.press(
                    "Enter",
                    timeout=3000
                )

                page.wait_for_timeout(
                    1500
                )

                return True

            except Exception:
                pass

        print(
            f"    Could not find location "
            f"input for {location}"
        )

    except Exception as e:

        print(
            f"    Store finder error: {e}"
        )

    return False


def main():

    products = toyworld_products()

    if not products:

        print(
            "No Toyworld TCG products "
            "found in products.json"
        )

        return

    alerts = []

    checked_pairs = set()

    print(
        f"Toyworld TCG products found: "
        f"{len(products)}"
    )

    print(
        f"Locations to check: "
        f"{len(SEARCH_LOCATIONS)}"
    )

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
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 "
                "Safari/537.36"
            ),
        )

        # -------------------------------------------------
        # Check each TCG product
        # -------------------------------------------------

        for product in products:

            print()
            print(
                "=============================="
            )

            print(
                f"Checking: "
                f"{product['name']}"
            )

            print(
                "=============================="
            )

            # Load product page once
            try:

                page.goto(
                    product["url"],
                    wait_until="domcontentloaded",
                    timeout=20000
                )

                page.wait_for_timeout(
                    2000
                )

            except Exception as e:

                print(
                    f"  Product page failed: {e}"
                )

                continue

            # -------------------------------------------------
            # Palmerston North
            # -------------------------------------------------

            for region, location in SEARCH_LOCATIONS:

                print(
                    f"  Checking "
                    f"{region} "
                    f"({location})..."
                )

                try:

                    found = search_location(
                        page,
                        location
                    )

                    if not found:

                        print(
                            "    Store search "
                            "could not be opened"
                        )

                        continue

                    # Give Toyworld time to update
                    page.wait_for_timeout(
                        1000
                    )

                    try:

                        body = page.locator(
                            "body"
                        ).inner_text(
                            timeout=5000
                        )

                        lines = clean_lines(
                            body
                        )

                        cards = find_store_cards(
                            lines
                        )

                    except Exception as e:

                        print(
                            f"    Could not read "
                            f"results: {e}"
                        )

                        continue

                    # -------------------------------------------------
                    # Process stores
                    # -------------------------------------------------

                    for store, status in cards:

                        key = (
                            product["name"],
                            store,
                            status
                        )

                        if key in checked_pairs:
                            continue

                        checked_pairs.add(
                            key
                        )

                        print(
                            f"    {region} | "
                            f"{store} | "
                            f"{status}"
                        )

                        # Only alert on actual store availability
                        if status in (
                            "AVAILABLE",
                            "CALL TO CONFIRM"
                        ):

                            alerts.append(
                                "🚨 TOYWORLD "
                                "PALMERSTON NORTH "
                                "TCG STOCK\n"
                                f"{product['name']}\n"
                                f"📍 {store}\n"
                                f"📦 {status}\n"
                                f"🛒 {product['url']}"
                            )

                except Exception as e:

                    print(
                        f"    {region}: "
                        f"ERROR {e}"
                    )

        browser.close()

    # -------------------------------------------------
    # Summary
    # -------------------------------------------------

    print()
    print(
        "=============================="
    )

    print(
        "TOYWORLD TCG REGIONAL SUMMARY"
    )

    print(
        "=============================="
    )

    print(
        f"TCG products checked: "
        f"{len(products)}"
    )

    print(
        f"Store-stock positives: "
        f"{len(alerts)}"
    )

    if alerts:

        send_telegram(
            "\n\n".join(alerts)[:3900]
        )

    else:

        print(
            "No confirmed Palmerston North "
            "AVAILABLE/CALL TO CONFIRM "
            "TCG results found."
        )


if __name__ == "__main__":
    main()
