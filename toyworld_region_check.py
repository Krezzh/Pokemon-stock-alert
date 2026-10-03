import json
import os
import requests


# ============================================================
# TOYWORLD PALMERSTON NORTH - POKÉMON 30TH STOCK CHECKER
# ============================================================

STOCK_URL = "https://stockinstore.net/stores/getStoresStock"

TOYWORLD_SITE = "10044"
TOYWORLD_WIDGET = "51"

PALMERSTON_NORTH_STORE = "1065"
PALMERSTON_NORTH_LATLONG = "-40.3583099_175.6125759"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


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


def send_telegram(message):
    """Send a Telegram notification."""

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not found.")
        return

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            data=payload,
            timeout=20,
        )

        print(f"Telegram status: {response.status_code}")

    except Exception as e:
        print(f"Telegram error: {e}")


def check_stock(product):
    """Check Palmerston North stock for one product."""

    name = product["name"]
    upc = product["upc"]

    print()
    print("=" * 55)
    print(f"Checking {name}")
    print(f"UPC: {upc}")
    print(
        "Store: Toyworld Palmerston North "
        f"({PALMERSTON_NORTH_STORE})"
    )

    payload = {
        "site": TOYWORLD_SITE,
        "widget": TOYWORLD_WIDGET,
        "timezoneOffsetMinutes": "780",
        "pid": upc,
        "storeids": PALMERSTON_NORTH_STORE,
        "latlong": PALMERSTON_NORTH_LATLONG,
        "preview": "false",
        "thresholdType": "cnc",
        "items": json.dumps(
            [
                {
                    "upc": upc,
                    "quantity": 1,
                }
            ]
        ),
        "lang": "en",
        "widgetType": "product",
        "info": "none",
        "isajax": "1",
    }

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
        print(f"ERROR checking {name}: {e}")
        return 0

    # --------------------------------------------------------
    # Toyworld returns the "response" field as JSON text.
    # Decode it if necessary.
    # --------------------------------------------------------

    response_data = data.get("response", [])

    if isinstance(response_data, str):
        try:
            response_data = json.loads(response_data)
        except json.JSONDecodeError:
            print("ERROR: Could not decode Toyworld response.")
            print(response_data[:1000])
            return 0

    # --------------------------------------------------------
    # The decoded response can be a list of stores or a
    # dictionary containing a stores list.
    # --------------------------------------------------------

    if isinstance(response_data, dict):
        stores = response_data.get("stores", [])
    elif isinstance(response_data, list):
        stores = response_data
    else:
        print("ERROR: Unexpected Toyworld response format.")
        print(f"Type: {type(response_data)}")
        return 0

    if not isinstance(stores, list):
        print("ERROR: Store data is not a list.")
        return 0

    # --------------------------------------------------------
    # Find Palmerston North
    # --------------------------------------------------------

    for store in stores:

        # Occasionally a store can itself be returned as
        # JSON text, so decode it if necessary.
        if isinstance(store, str):
            try:
                store = json.loads(store)
            except json.JSONDecodeError:
                continue

        if not isinstance(store, dict):
            continue

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

        store_name = store.get(
            "store_name",
            "Toyworld Palmerston North",
        )

        print(f"Store: {store_name}")
        print(f"Stock reported: {stock}")

        # ----------------------------------------------------
        # Alert if stock is reported
        # ----------------------------------------------------

        if stock > 0:

            message = (
                "🚨 TOYWORLD POKÉMON 30TH STOCK!\n\n"
                f"📦 {name}\n"
                "📍 Toyworld Palmerston North\n"
                f"📊 Reported stock: {stock}\n"
                f"🔢 UPC: {upc}\n\n"
                "⚠️ Stock can change quickly. "
                "Confirm with the store before travelling."
            )

            send_telegram(message)

        return stock

    print(
        "Toyworld Palmerston North was not found "
        "in the response."
    )

    return 0


def main():
    print()
    print("=" * 55)
    print("TOYWORLD PALMERSTON NORTH - 30TH POKÉMON STOCK CHECK")
    print("=" * 55)

    for product in PRODUCTS:
        stock = check_stock(product)

        print(
            f"Finished: {product['name']} "
            f"| Stock: {stock}"
        )

    print()
    print("=" * 55)
    print("TOYWORLD CHECK COMPLETE")
    print("=" * 55)


if __name__ == "__main__":
    main()
