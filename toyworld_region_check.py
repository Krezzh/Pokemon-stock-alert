import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PRODUCTS_FILE = Path("products.json")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# NZ regions used to group store results.
REGION_KEYWORDS = {
    "Northland": ["whangarei", "kerikeri"],
    "Auckland": ["auckland", "manukau", "albany", "glenfield", "milford", "westgate", "northwest", "howick", "botany"],
    "Waikato": ["hamilton", "chartwell", "cambridge", "te awamutu", "tauranga"],  # Tauranga handled below if store text says Bay of Plenty
    "Bay of Plenty": ["tauranga", "mount maunganui", "te puke", "whakatane", "rotorua"],
    "Gisborne": ["gisborne"],
    "Hawke's Bay": ["napier", "hastings", "taradale"],
    "Taranaki": ["new plymouth", "new plymouth", "hawera", "stratford"],
    "Manawatu-Whanganui": ["palmerston north", "whanganui", "feilding", "levin"],
    "Wellington": ["wellington", "lower hutt", "upper hutt", "porirua", "petone", "johnsonville"],
    "Tasman": ["nelson", "richmond"],
    "Marlborough": ["blenheim"],
    "West Coast": ["greymouth", "hokitika", "westport"],
    "Canterbury": ["christchurch", "riccarton", "hornby", "marshland", "ashburton", "timaru"],
    "Otago": ["dunedin", "queenstown", "wanaka", "oamaru"],
    "Southland": ["invercargill", "gore"],
}

def region_for_store(text):
    t = text.lower()
    # Prefer the more specific Bay of Plenty classification for Tauranga/Rotorua.
    if any(k in t for k in REGION_KEYWORDS["Bay of Plenty"]):
        return "Bay of Plenty"
    for region, keys in REGION_KEYWORDS.items():
        if any(k in t for k in keys):
            return region
    return "Other NZ"

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }, timeout=20)

def load_toyworld_products():
    with PRODUCTS_FILE.open("r", encoding="utf-8") as f:
        products = json.load(f)
    return [p for p in products if p.get("retailer") == "Toyworld NZ"]

def extract_store_results(page):
    # The stockinstore widget is rendered client-side. We deliberately inspect
    # rendered text rather than relying on a private API endpoint.
    text = page.locator("body").inner_text(timeout=15000)
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]

    hits = []
    statuses = ("AVAILABLE", "CALL TO CONFIRM", "OUT OF STOCK")
    for i, line in enumerate(lines):
        upper = line.upper()
        if any(s in upper for s in statuses):
            window = " | ".join(lines[max(0, i-4):min(len(lines), i+5)])
            if "TOYWORLD" in window.upper() or "AVAILABLE" in upper or "CALL TO CONFIRM" in upper:
                hits.append((line, window))
    return hits

def main():
    products = load_toyworld_products()
    if not products:
        print("No Toyworld NZ products found in products.json")
        return

    alerts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        )

        for product in products:
            print(f"\nChecking regional stock: {product['name']}")
            try:
                page.goto(product["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)

                # Give the stock-in-store widget time to initialise.
                for _ in range(3):
                    if "STOCK" in page.locator("body").inner_text(timeout=10000).upper():
                        break
                    page.wait_for_timeout(2500)

                hits = extract_store_results(page)

                # Keep only likely stock-in-store lines, then group by region.
                region_hits = {}
                for status_line, window in hits:
                    region = region_for_store(window)
                    region_hits.setdefault(region, []).append((status_line, window))

                print("Regional results:")
                for region, values in sorted(region_hits.items()):
                    for status_line, window in values:
                        print(f"  {region}: {status_line} | {window[:220]}")

                # Alert only on positive/low-stock signals.
                positives = []
                for region, values in region_hits.items():
                    for status_line, window in values:
                        u = status_line.upper()
                        if "AVAILABLE" in u or "CALL TO CONFIRM" in u:
                            positives.append((region, status_line, window))

                if positives:
                    msg = [f"🚨 TOYWORLD IN-STORE STOCK", product["name"], product["url"], ""]
                    for region, status_line, window in positives[:20]:
                        msg.append(f"📍 {region}: {status_line}")
                    alerts.append("\n".join(msg))

            except Exception as e:
                print(f"ERROR {product['name']}: {e}")

        browser.close()

    print("\n=== TOYWORLD REGIONAL SUMMARY ===")
    print(f"Products checked: {len(products)}")
    print(f"Positive regional alerts: {len(alerts)}")

    # Avoid sending a Telegram message for every store/card; send one grouped alert.
    if alerts:
        send_telegram("\n\n".join(alerts)[:3900])
    else:
        print("No AVAILABLE or CALL TO CONFIRM Toyworld regional stock found.")

if __name__ == "__main__":
    main()
              
