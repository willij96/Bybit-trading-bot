import requests
import time
import hashlib
import hmac
import uuid
import json
from flask import Flask, request, jsonify
import os

# 🔹 Bybit API Credentials (Testnet)
API_KEY = "VdeQh5iTSVdV68tBH9"
API_SECRET = "QiaxJnhjMGYLobY42goDLGZbOtE4GZdDMZYS"
BYBIT_URL = "https://api-testnet.bybit.com"
RECV_WINDOW = "5000"  # Default recv_window

# 🔹 Flask Webhook Server
app = Flask(__name__)

# Function to generate the signature
def gen_signature(payload):
    """Generate the HMAC SHA256 signature for the request."""
    time_stamp = str(int(time.time() * 10 ** 3))  # Timestamp in milliseconds
    param_str = time_stamp + API_KEY + RECV_WINDOW + payload
    signature = hmac.new(bytes(API_SECRET, "utf-8"), param_str.encode("utf-8"), hashlib.sha256).hexdigest()
    return signature, time_stamp

# Function to send the HTTP request
def http_request(endpoint, method, payload, info):
    """Send the HTTP request with the necessary headers and payload."""
    signature, time_stamp = gen_signature(payload)
    headers = {
        'X-BAPI-API-KEY': API_KEY,
        'X-BAPI-SIGN': signature,
        'X-BAPI-SIGN-TYPE': '2',
        'X-BAPI-TIMESTAMP': time_stamp,
        'X-BAPI-RECV-WINDOW': RECV_WINDOW,
        'Content-Type': 'application/json'
    }

    if method == "POST":
        response = requests.post(f"{BYBIT_URL}{endpoint}", headers=headers, data=payload)
    else:  # GET request
        response = requests.get(f"{BYBIT_URL}{endpoint}?{payload}", headers=headers)

    print(f"{info} Response: {response.text}")
    print(f"Elapsed Time: {response.elapsed}")
    return response.json()

# Function to get the current position
def get_current_position(symbol="BTCUSDT"):
    """Fetch the current position on Bybit."""
    params = {
        "api_key": API_KEY,
        "symbol": symbol,
        "category": "linear",  # Add category parameter
        "timestamp": str(int(time.time() * 1000)),
        "recv_window": RECV_WINDOW
    }
    payload = f"api_key={API_KEY}&symbol={symbol}&category=linear&timestamp={params['timestamp']}&recv_window={RECV_WINDOW}"
    response = http_request("/v5/position/list", "GET", payload, "Current Position")
    try:
        return response["result"]["list"]
    except KeyError:
        print("⚠️ No position data found or error occurred.")
        return []

# Function to close the current position
def close_position(symbol="BTCUSDT"):
    """Close the current position on Bybit."""
    current_position = get_current_position(symbol)
    
    if current_position:
        side = current_position[0].get("side", "")  # Get the side if available
        if side:  # If there's a side, we can close the position
            opposite_side = "Sell" if side == "Buy" else "Buy"  # Opposite side to close position
            print(f"💥 Closing current position to {opposite_side}...")
            qty = current_position[0]["size"]
            place_order(opposite_side, symbol, qty)  # Close the position by placing an order with opposite side
        else:
            print("⚠️ No side found, cannot determine the position.")
    else:
        print("⚠️ No open position to close.")

# Function to place an order
def place_order(side, symbol="BTCUSDT", qty=0.01, price=None):
    """Place a market order (long or short) on Bybit."""
    order_link_id = uuid.uuid4().hex  # Unique order identifier

    params = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Limit" if price else "Market",  # If price is provided, use Limit order
        "qty": str(qty),
        "price": str(price) if price else "",  # Add price only if it's a Limit order
        "timeInForce": "GoodTillCancel",
        "orderLinkId": order_link_id
    }

    payload = json.dumps(params)
    endpoint = "/v5/order/create"
    return http_request(endpoint, "POST", payload, "Create Order")

# 🔹 Webhook Endpoint for TradingView Alerts
@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle TradingView alerts."""
    data = request.json
    print(f"📩 Received TradingView alert: {data}")

    if not data or "signal" not in data:
        return jsonify({"error": "Invalid alert format"}), 400

    signal = data["signal"].lower()

    if signal == "long":
        print("🚀 Long signal detected! Placing BUY order...")
        close_position()  # Close any existing position
        place_order("Buy")
    elif signal == "short":
        print("🔻 Short signal detected! Placing SELL order...")
        close_position()  # Close any existing position
        place_order("Sell")
    else:
        print("⚠️ Unknown signal, ignoring...")

    return jsonify({"status": "success"}), 200

# 🔹 Start Flask Server
if __name__ == "__main__":
    print("🚀 Trading Bot Started... Listening for TradingView Alerts...")
    port = int(os.environ.get("PORT", 5000))  # Get the port from the environment, default to 5000 for local testing
    app.run(host="0.0.0.0", port=port)
