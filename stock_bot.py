import json
import os
import re
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PokemonStockAlert/1.0; +https://github.com/)"
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
    m = re.search(r'\$\s?\d+(?:[.,]\d{2})?', text)
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
                    stack.extend(offers if isinstance(offers, list) else [offers])
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
        if "sold out" in lower:
            return False, extract_price(soup, text)
        return (("add to cart" in lower or "add to bag" in lower or "in stock" in lower),
                extract_price(soup, text))

    if rules == "kmart":
        if "out of stock online" in lower or "out of stock" in lower:
            return False, extract_price(soup, text)
        return (("add to bag" in lower or "in stock" in lower),
                extract_price(soup, text))

    if rules == "warehouse":
        if "in-store only" in lower or "out of stock" in lower or "sold out" in lower:
            return False, extract_price(soup, text)
        return (("add to cart" in lower or "add to bag" in lower or "buy now" in lower),
                extract_price(soup, text))

    return False, extract_price(soup, text)

def telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": False,
    }, timeout=30)
    r.raise_for_status()

def main():
    state = load_state()
    new_state = dict(state)

    for product in PRODUCTS:
        key = product["url"]
        try:
            r = requests.get(product["url"], headers=HEADERS, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            available, price = detect(product, soup)
        except Exception as e:
            print(f"ERROR {product['name']}: {e}")
            continue

        previous = state.get(key, {}).get("available")
        new_state[key] = {"available": available, "price": price}

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

        print(f"{product['retailer']} | {product['name']} | available={available}")

    save_state(new_state)

if __name__ == "__main__":
    main()
