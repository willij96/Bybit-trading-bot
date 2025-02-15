import requests
import time
import hashlib
import hmac
import uuid
import json
import os
from flask import Flask, request, jsonify

# 🔹 Bybit API Credentials (Testnet)
API_KEY = "leeKsmIT4EjU9WhveF"
API_SECRET = "vhoElOAgSa5MdHMJUjVDdeA1OcMMnG0erFYb"
BYBIT_URL = "https://api.bybit.com"
RECV_WINDOW = "5000"  # Default recv_window

# 🔹 Flask Webhook Server
app = Flask(__name__)

# Function to generate API signature
def gen_signature(payload):
    time_stamp = str(int(time.time() * 1000))
    param_str = time_stamp + API_KEY + RECV_WINDOW + payload
    signature = hmac.new(API_SECRET.encode(), param_str.encode(), hashlib.sha256).hexdigest()
    return signature, time_stamp

# Function to send HTTP requests
def http_request(endpoint, method, payload, description):
    signature, time_stamp = gen_signature(payload)
    headers = {
        'X-BAPI-API-KEY': API_KEY,
        'X-BAPI-SIGN': signature,
        'X-BAPI-SIGN-TYPE': '2',
        'X-BAPI-TIMESTAMP': time_stamp,
        'X-BAPI-RECV-WINDOW': RECV_WINDOW,
        'Content-Type': 'application/json'
    }
    
    url = f"{BYBIT_URL}{endpoint}"
    response = requests.post(url, headers=headers, data=payload) if method == "POST" else requests.get(f"{url}?{payload}", headers=headers)
    
    print(f"\n🔹 {description} Response: {response.text}\n")
    return response.json()

# Function to get account balance
def get_account_balance(coin="USDT"):
    response = http_request("/v5/account/wallet-balance", "GET", f"accountType=UNIFIED&coin={coin}", "Fetching Account Balance")
    if response.get("retCode") != 0:
        print(f"⚠️ Error Fetching Balance: {response.get('retMsg')}")
        return None
    
    try:
        balance_data = response["result"]["list"][0]["coin"]
        for asset in balance_data:
            if asset["coin"] == coin:
                available_balance = float(asset["availableToWithdraw"]) if asset["availableToWithdraw"] else float(asset["walletBalance"])
                print(f"💰 Available {coin} Balance: {available_balance}")
                return available_balance
    except Exception as e:
        print(f"⚠️ Balance Fetch Error: {e}")
    return None

# Function to get market price
def get_market_price(symbol="XLMUSDT"):
    response = http_request("/v5/market/tickers", "GET", f"category=linear&symbol={symbol}", "Fetching Market Price")
    try:
        price = float(response["result"]["list"][0]["lastPrice"])
        print(f"📈 Market Price of {symbol}: {price}")
        return price
    except Exception as e:
        print(f"⚠️ Market Price Fetch Error: {e}")
    return None

# Function to get open position
def get_position(symbol="XLMUSDT"):
    response = http_request("/v5/position/list", "GET", f"symbol={symbol}&category=linear", "Fetching Position Data")
    
    # Debugging: Print the raw response to check its format
    print(f"🔹 Position Data Response: {response}")
    
    if isinstance(response, str):  # If response is a string, try to parse it as JSON
        try:
            response = json.loads(response)  # Convert string to a dictionary
            print(f"🔹 Parsed Response: {response}")
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON Decode Error: {e}")
            return None, None
    
    if response.get("retCode") != 0:
        print(f"⚠️ Error fetching position data: {response.get('retMsg')}")
        return None, None
    
    try:
        positions = response["result"]["list"]  # Access the list of positions

        if not positions:
            print(f"⚠️ No position found for {symbol}.")
            return None, None
        
        for pos in positions:
            if pos["symbol"] == symbol:
                position_size = float(pos["size"])  # Get the position size (amount of the asset)
                side = pos["side"]  # 'Buy' or 'Sell' (for long or short positions)
                return position_size, side
    except Exception as e:
        print(f"⚠️ Error extracting position data: {e}")
    
    return None, None  # Default if no position found




# Function to close the current position
def close_position(symbol="XLMUSDT"):
    position_size, side = get_position(symbol)
    
    if position_size is None or position_size == 0:
        print(f"❌ No active position found for {symbol}, cannot close.")
        return True  # No position to close, considered successful
    
    # Determine the side to close the position
    opposite_side = "Sell" if side == "Buy" else "Buy"
    qty = position_size  # Use the exact position size to close it
    
    print(f"🔹 Closing {side} Position. Qty: {qty} {symbol} on opposite side ({opposite_side})")

    order_link_id = uuid.uuid4().hex
    params = {
        "category": "linear",
        "symbol": symbol,
        "side": opposite_side,  # Opposite side to close the position
        "orderType": "Market",
        "qty": str(qty),  # Use the exact position size
        "timeInForce": "GoodTillCancel",
        "orderLinkId": order_link_id
    }
    
    payload = json.dumps(params)
    response = http_request("/v5/order/create", "POST", payload, f"Closing {side} Position")
    
    if response.get("retCode") != 0:
        print(f"⚠️ Error closing position: {response.get('retMsg')}")
        return False  # Error occurred while closing position
    else:
        print(f"🔹 Successfully closed {side} position of {qty} {symbol}")
        return True  # Successfully closed position

# Function to place a new order after closing the old position
def place_order(side, symbol="XLMUSDT", price=None, max_retries=3):
    balance = get_account_balance("USDT")
    if not balance:
        print("❌ Cannot retrieve balance, order aborted.")
        return

    market_price = get_market_price(symbol)
    if not market_price:
        print("❌ Cannot retrieve market price, order aborted.")
        return

    amount_to_trade = balance
    min_order_value = 5
    if amount_to_trade < min_order_value:
        print(f"❌ Insufficient balance! Your balance {amount_to_trade} USDT is below Bybit's minimum order value of 5 USDT.")
        return
    
    qty = round(amount_to_trade / market_price)
    order_value = qty * market_price

    if order_value < min_order_value:
        print(f"❌ Order value {order_value:.2f} USDT is still below 5 USDT after calculation, cannot place order.")
        return
    
    print(f"🔹 Using 100% Balance: {balance:.2f} USDT → Trading {qty} {symbol} (Order Value: {order_value:.2f} USDT)") 

    order_link_id = uuid.uuid4().hex
    params = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Limit" if price else "Market",
        "qty": str(qty),
        "price": str(price) if price else "",
        "timeInForce": "GoodTillCancel",
        "orderLinkId": order_link_id
    }

    payload = json.dumps(params)
    
    # Retry mechanism
    for attempt in range(1, max_retries + 1):
        response = http_request("/v5/order/create", "POST", payload, f"Placing {side} Order (Attempt {attempt})")

        if response.get("retCode") == 0:
            print(f"✅ Order placed successfully on attempt {attempt}")
            return
        else:
            print(f"⚠️ Error placing order: {response.get('retMsg')} (Attempt {attempt}/{max_retries})")
            time.sleep(2)  # Wait before retrying
    
    print("❌ Order failed after multiple retries. Check Bybit logs.")

# Function to get open orders using the `/v5/order/realtime` endpoint
def get_open_orders(symbol="XLMUSDT"):
    payload = f"symbol={symbol}&category=linear&openOnly=0&limit=1"
    response = http_request("/v5/order/realtime", "GET", payload, "Fetching Open Orders")
    
    if response.get("retCode") != 0:
        print(f"⚠️ Error fetching open orders: {response.get('retMsg')}")
        return None
    
    try:
        # Assuming the result will contain a list of orders
        orders = response.get("result", [])
        if not orders:
            print(f"⚠️ No open orders found for {symbol}.")
            return None
        
        print(f"🔹 Open Orders: {orders}")
        return orders
    except Exception as e:
        print(f"⚠️ Error processing open orders: {e}")
    
    return None


# Webhook for TradingView alerts
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print(f"📩 TradingView Alert Received: {data}")
    
    if not data or "signal" not in data:
        return jsonify({"error": "Invalid alert format"}), 400
    
    signal = data["signal"].lower()
    
    # Close the current position before placing the new one
    if not close_position(symbol="XLMUSDT"):
        print("❌ Failed to close the current position, aborting new order.")
        return jsonify({"error": "Failed to close the position"}), 500

    # Place the new order after closing the old position
    if signal == "long":
        print("🚀 Long Signal Detected! Placing BUY order...")
        place_order("Buy")
    elif signal == "short":
        print("🔻 Short Signal Detected! Placing SELL order...")
        place_order("Sell")
    else:
        print("⚠️ Unknown signal received, ignoring...")
    
    return jsonify({"status": "success"}), 200

# Start Flask Server
if __name__ == "__main__":
    print("🚀 Trading Bot Started... Listening for TradingView Alerts...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
