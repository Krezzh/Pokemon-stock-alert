import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = Path("state.json")
PRODUCTS_FILE = Path("products.json")


def load_products():
    return json.loads(PRODUCTS_FILE.read_text())


PRODUCTS = load_products()

# More browser-like headers. Some NZ retailers reject the old bot-style
# User-Agent used by the previous version.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-NZ,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def extract_price(soup, text):
    # Prefer JSON-LD product offers.
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            offers = item.get("offers")
            if isinstance(offers, dict):
                price = offers.get("price")
                if price:
                    currency = offers.get("priceCurrency", "NZD")
                    return f"${price} {currency}" if currency != "NZD" else f"${price}"

    m = re.search(r"\$\s?\d+(?:[.,]\d{2})?", text)
    return m.group(0).replace(" ", "") if m else None


def jsonld_availability(soup):
    values = []

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue

        stack = data if isinstance(data, list) else [data]

        while stack:
            item = stack.pop()

            if isinstance(item, dict):
                if "offers" in item:
                    offers = item["offers"]
                    stack.extend(
                        offers if isinstance(offers, list) else [offers]
                    )

                availability = item.get("availability")
                if availability:
                    values.append(str(availability).lower())

            elif isinstance(item, list):
                stack.extend(item)

    return " ".join(values)


def detect(product, soup):
    text = soup.get_text(" ", strip=True)
    lower = text.lower()
    availability = jsonld_availability(soup)

    if "outofstock" in availability or "out of stock" in availability:
        return False, extract_price(soup, text)

    if "instock" in availability or "in stock" in availability:
        return True, extract_price(soup, text)

    rules = product["rules"]

    if rules == "mightyape":
        if "sold out" in lower or "out of stock" in lower:
            return False, extract_price(soup, text)

        return (
            "add to cart" in lower
            or "add to bag" in lower
            or "in stock" in lower
        ), extract_price(soup, text)

    if rules == "kmart":
        if "out of stock online" in lower or "out of stock" in lower:
            return False, extract_price(soup, text)

        return (
            "add to bag" in lower
            or "in stock" in lower
        ), extract_price(soup, text)

    if rules == "warehouse":
        if (
            "in-store only" in lower
            or "out of stock" in lower
            or "sold out" in lower
        ):
            return False, extract_price(soup, text)

        return (
            "add to cart" in lower
            or "add to bag" in lower
            or "buy now" in lower
        ), extract_price(soup, text)

    if rules == "jbhifi":
        if "out of stock" in lower or "sold out" in lower:
            return False, extract_price(soup, text)

        return (
            "add to cart" in lower
            or "add to bag" in lower
            or "buy now" in lower
            or "in stock" in lower
        ), extract_price(soup, text)

    # Generic Shopify-style pages such as PokeStash.
    if rules == "generic":
        if "sold out" in lower or "out of stock" in lower:
            return False, extract_price(soup, text)

        return (
            "add to cart" in lower
            or "add to bag" in lower
            or "buy now" in lower
            or "in stock" in lower
        ), extract_price(soup, text)

    return False, extract_price(soup, text)


def fetch_page(session, url):
    """
    Try a page a few times. Returns:
      (response, status_label)

    status_label is one of:
      OK, BLOCKED, NOT_FOUND, ERROR
    """
    last_response = None
    last_error = None

    for attempt in range(3):
        try:
            response = session.get(
                url,
                headers=HEADERS,
                timeout=30,
                allow_redirects=True,
            )
            last_response = response

            if response.status_code == 200:
                return response, "OK"

            if response.status_code == 403:
                # A short retry can help with temporary edge protection.
                if attempt < 2:
                    time.sleep(2 + attempt * 2)
                    continue
                return response, "BLOCKED"

            if response.status_code == 404:
                # Retry once because some retailer edges return transient 404s.
                if attempt == 0:
                    time.sleep(2)
                    continue
                return response, "NOT_FOUND"

            if response.status_code >= 500:
                if attempt < 2:
                    time.sleep(2 + attempt * 2)
                    continue
                return response, "ERROR"

            response.raise_for_status()

        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 + attempt * 2)
                continue

    if last_response is not None:
        return last_response, "ERROR"

    raise last_error or RuntimeError("Unknown request error")


def telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    r = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    r.raise_for_status()


def main():
    state = load_state()
    new_state = dict(state)

    session = requests.Session()

    counts = {
        "available": 0,
        "out_of_stock": 0,
        "blocked": 0,
        "not_found": 0,
        "error": 0,
    }

    for product in PRODUCTS:
        key = product["url"]

        try:
            response, status = fetch_page(session, product["url"])

            if status == "BLOCKED":
                counts["blocked"] += 1
                print(
                    f"BLOCKED {product['retailer']} | "
                    f"{product['name']} | HTTP {response.status_code}"
                )
                continue

            if status == "NOT_FOUND":
                counts["not_found"] += 1
                print(
                    f"NOT_FOUND {product['retailer']} | "
                    f"{product['name']} | HTTP {response.status_code}"
                )
                continue

            if status != "OK":
                counts["error"] += 1
                print(
                    f"ERROR {product['retailer']} | "
                    f"{product['name']} | HTTP {response.status_code}"
                )
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            available, price = detect(product, soup)

        except Exception as e:
            counts["error"] += 1
            print(
                f"ERROR {product['retailer']} | "
                f"{product['name']} | {e}"
            )
            continue

        previous = state.get(key, {}).get("available")
        new_state[key] = {
            "available": available,
            "price": price,
        }

        if available:
            counts["available"] += 1
            stock_status = "AVAILABLE"
        else:
            counts["out_of_stock"] += 1
            stock_status = "OUT_OF_STOCK"

        # Alert on a transition to available, or on first run if already available.
        if available and previous is not True:
            price_line = f"\n💰 {price}" if price else ""

            message = (
                "🟢 POKÉMON 30TH STOCK ALERT\n\n"
                f"🏪 {product['retailer']}\n"
                f"📦 {product['name']}{price_line}\n\n"
                f"🛒 {product['url']}"
            )

            try:
                telegram(message)
                print(f"ALERT: {product['name']}")
            except Exception as e:
                print(f"TELEGRAM ERROR: {e}")

        print(
            f"{stock_status} {product['retailer']} | "
            f"{product['name']}"
            + (f" | {price}" if price else "")
        )

    print("\n========== STOCK CHECK SUMMARY ==========")
    print(f"AVAILABLE:    {counts['available']}")
    print(f"OUT OF STOCK: {counts['out_of_stock']}")
    print(f"BLOCKED:      {counts['blocked']}")
    print(f"NOT FOUND:    {counts['not_found']}")
    print(f"ERROR:        {counts['error']}")
    print("=========================================")

    save_state(new_state)


if __name__ == "__main__":
    main()
