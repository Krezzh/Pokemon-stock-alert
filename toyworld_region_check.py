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

STATE_FILE = "toyworld_state.json"

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


def load_state():
    """Load the previous Toyworld stock values."""

    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception as e:
        print(f"Could not load Toyworld state: {e}")

    return {}


def save_state(state):
    """Save the current Toyworld stock values."""

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        print("Toyworld stock state saved.")

    except Exception as e:
        print(f"Could not save Toyworld state: {e}")


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
        "items": json.dumps([
            {
                "upc": upc,
                "quantity": 1,
            }
        ]),
        "lang": "en",
        "widgetType": "product",
        "info": "none",
        "isajax": "1",
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.toyworld.co.nz",
        "Referer": "https://www.toyworld.co.nz/",
        "X-Requested-With": "XMLHttpRequest",
    }

    try:

        response = requests.post(
            STOCK_URL,
            data=payload,
            headers=headers,
            timeout=30,
        )

        print(f"HTTP status: {response.status_code}")

        response.raise_for_status()

        data = response.json()

    except Exception as e:

        print(f"ERROR checking {name}: {e}")

        # None means the check failed.
        # We must NOT treat an error as zero stock.
        return None

    response_data = data.get("response", [])

    # Toyworld returns the response as JSON text.
    if isinstance(response_data, str):

        try:
            response_data = json.loads(response_data)

        except json.JSONDecodeError:

            print("ERROR: Could not decode Toyworld response.")
            print(response_data[:1000])

            return None

    if isinstance(response_data, dict):

        stores = response_data.get("stores", [])

    elif isinstance(response_data, list):

        stores = response_data

    else:

        print("ERROR: Unexpected Toyworld response format.")

        return None

    if not isinstance(stores, list):

        print("ERROR: Store data is not a list.")

        return None

    # --------------------------------------------------------
    # Find Palmerston North
    # --------------------------------------------------------

    for store in stores:

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

        return stock

    print(
        "Toyworld Palmerston North was not found "
        "in the response."
    )

    return None


def main():

    print()
    print("=" * 55)
    print("TOYWORLD PALMERSTON NORTH - 30TH POKÉMON STOCK CHECK")
    print("=" * 55)

    # Load previous stock
    previous_state = load_state()

    # Start with a copy so successful checks can update it.
    new_state = dict(previous_state)

    for product in PRODUCTS:

        name = product["name"]
        upc = product["upc"]

        current_stock = check_stock(product)

        # ----------------------------------------------------
        # API/check failed
        # ----------------------------------------------------

        if current_stock is None:

            print(
                f"Stock check failed for {name}. "
                "Keeping previous state."
            )

            continue

        # ----------------------------------------------------
        # Previous stock
        # ----------------------------------------------------

        previous_stock = previous_state.get(upc)

        print(
            f"Previous stock: {previous_stock}"
        )

        print(
            f"Current stock: {current_stock}"
        )

        # ----------------------------------------------------
        # Save current stock
        # ----------------------------------------------------

        new_state[upc] = current_stock

        # ----------------------------------------------------
        # Decide whether to send Telegram
        # ----------------------------------------------------

        if previous_stock is None:

            # First ever check.
            # Alert if stock is already available.

            if current_stock > 0:

                message = (
                    "🚨 TOYWORLD POKÉMON 30TH STOCK!\n\n"
                    f"📦 {name}\n"
                    "📍 Toyworld Palmerston North\n"
                    f"📊 Reported stock: {current_stock}\n"
                    f"🔢 UPC: {upc}\n\n"
                    "⚠️ Stock can change quickly. "
                    "Confirm with the store before travelling."
                )

                send_telegram(message)

        elif current_stock != previous_stock:

            # Stock changed since the previous check.
            # Only alert when there is currently stock.

            if current_stock > 0:

                message = (
                    "🚨 TOYWORLD POKÉMON 30TH STOCK CHANGE!\n\n"
                    f"📦 {name}\n"
                    "📍 Toyworld Palmerston North\n"
                    f"📊 Previous: {previous_stock}\n"
                    f"📦 Now: {current_stock}\n"
                    f"🔢 UPC: {upc}\n\n"
                    "⚠️ Stock can change quickly. "
                    "Confirm with the store before travelling."
                )

                send_telegram(message)

            else:

                print(
                    f"{name} is now out of stock."
                )

        else:

            print(
                f"No stock change for {name}. "
                "No Telegram alert."
            )

    # --------------------------------------------------------
    # Save state after all products have been checked.
    # --------------------------------------------------------

    save_state(new_state)

    print()
    print("=" * 55)
    print("TOYWORLD CHECK COMPLETE")
    print("=" * 55)


if __name__ == "__main__":
    main()
