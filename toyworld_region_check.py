import json
import os
from pathlib import Path

import requests


# ============================================================
# TOYWORLD STOCK-IN-STORE SETTINGS
# ============================================================

STOCK_URL = "https://stockinstore.net/stores/getStoresStock"

TOYWORLD_SITE = "10044"
TOYWORLD_WIDGET = "51"

# Toyworld Palmerston North
PALMERSTON_NORTH_STORE = "1065"

# Store coordinates from Toyworld's Stockinstore data
PALMERSTON_NORTH_LATLONG = "-40.3583099_175.6125759"


# ============================================================
# PRODUCTS WE WANT TO WATCH
# ============================================================

PRODUCTS = [
    {
        "name": "Pokémon TCG 30th Celebration Booster Bundle",
        "upc": "196214158849",
    },
    {
        "name": "Pokémon TCG 30th Celebration Mini Tin (Assorted)",
        "upc": "196214159082",
    },
]


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )

        print(f"Telegram status: {response.status_code}")

    except Exception as e:
        print(f"Telegram error: {e}")


# ============================================================
# STOCK CHECK
# ============================================================

def check_stock(product):
    upc = product["upc"]

    payload = {
        "site": TOYWORLD_SITE,
        "widget": TOYWORLD_WIDGET,
        "timezoneOffsetMinutes": "780",
        "pid": upc,
        "storeids": PALMERSTON_NORTH_STORE,
        "latlong": PALMERSTON_NORTH_LATLONG,
        "preview": "false",
        "thresholdType": "cnc",
        "items": json.dumps([
            {
                "upc": upc,
                "quantity": 1
            }
        ]),
        "lang": "en",
        "widgetType": "product",
        "info": "none",
        "isajax": "1",
    }

    print(f"\nChecking {product['name']}")
    print(f"UPC: {upc}")
    print("Store: Toyworld Palmerston North (1065)")

    try:
        response = requests.post(
            STOCK_URL,
            data=payload,
            timeout=30,
        )

        print(f"HTTP status: {response.status_code}")

        response.raise_for_status()

        data = response.json()

    except Exception as e:
        print(f"ERROR checking {product['name']}: {e}")
        return None

    stores = data.get("response", [])

    for store in stores:
        store_code = str(
            store.get("code")
            or store.get("gmb_store_code")
            or ""
        )

        if store_code != PALMERSTON_NORTH_STORE:
            continue

        stock_raw = store.get("stock", "0")

        try:
            stock = int(float(stock_raw))
        except (TypeError, ValueError):
            stock = 0

        print(f"Store: {store.get('store_name', 'Toyworld Palmerston North')}")
        print(f"Stock reported: {stock}")

        return stock

    print("Palmerston North store was not found in the response.")
    return None


# ============================================================
# MAIN
# ============================================================

def main():

    alerts = []

    print("=" * 60)
    print("TOYWORLD PALMERSTON NORTH - 30TH POKÉMON STOCK CHECK")
    print("=" * 60)

    for product in PRODUCTS:

        stock = check_stock(product)

        if stock is None:
            continue

        if stock > 0:

            message = (
                "🚨 TOYWORLD POKÉMON 30TH STOCK!\n\n"
                f"📦 {product['name']}\n"
                f"📍 Toyworld Palmerston North\n"
                f"🔢 Reported stock: {stock}\n"
                f"🏷️ UPC: {product['upc']}\n\n"
                "⚠️ Toyworld stock data can change quickly — "
                "confirm with the store before travelling."
            )

            alerts.append(message)

        else:
            print(f"❌ OUT OF STOCK: {product['name']}")

    print("\n" + "=" * 60)
    print(f"Products checked: {len(PRODUCTS)}")
    print(f"Positive stock alerts: {len(alerts)}")
    print("=" * 60)

    if alerts:
        send_telegram("\n\n".join(alerts))
    else:
        print("No Palmerston North stock found.")


if __name__ == "__main__":
    main()
