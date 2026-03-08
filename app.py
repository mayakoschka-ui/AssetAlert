import os
import time
import threading
import logging
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import yfinance as yf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Cache to avoid hammering yfinance
price_cache = {
    "gold": {"price": None, "currency": "USD", "timestamp": 0},
    "silver": {"price": None, "currency": "USD", "timestamp": 0},
    "bitcoin": {"price": None, "currency": "USD", "timestamp": 0},
}
cache_lock = threading.Lock()
CACHE_TTL = 55  # seconds — refresh slightly under 60s client cycle

SYMBOLS = {
    "gold": "GC=F",
    "silver": "SI=F",
    "bitcoin": "BTC-USD",
}

def fetch_price(asset: str) -> float | None:
    symbol = SYMBOLS.get(asset)
    if not symbol:
        return None
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d", interval="1m")
        if data.empty:
            # fallback: fast_info
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            return float(price) if price else None
        return float(data["Close"].iloc[-1])
    except Exception as e:
        logger.warning(f"Error fetching {asset}: {e}")
        return None

def refresh_cache():
    """Background thread: keep prices warm so /api/prices is instant."""
    while True:
        for asset in SYMBOLS:
            try:
                price = fetch_price(asset)
                with cache_lock:
                    if price is not None:
                        price_cache[asset]["price"] = price
                        price_cache[asset]["timestamp"] = time.time()
                        logger.info(f"Cached {asset}: {price:.2f}")
            except Exception as e:
                logger.error(f"Cache refresh error for {asset}: {e}")
            time.sleep(2)  # stagger requests to avoid rate limits
        # Wait before next full cycle; target ~50s between full refreshes
        time.sleep(40)

# Start background refresh thread
refresh_thread = threading.Thread(target=refresh_cache, daemon=True)
refresh_thread.start()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/prices")
def get_prices():
    result = {}
    now = time.time()
    with cache_lock:
        for asset, data in price_cache.items():
            age = now - data["timestamp"] if data["timestamp"] else None
            result[asset] = {
                "price": data["price"],
                "currency": data["currency"],
                "age_seconds": round(age, 1) if age is not None else None,
                "stale": age is None or age > 120,
            }
    return jsonify(result)

@app.route("/api/price/<asset>")
def get_single_price(asset):
    asset = asset.lower()
    if asset not in SYMBOLS:
        return jsonify({"error": "Unknown asset"}), 404
    with cache_lock:
        data = price_cache[asset]
        now = time.time()
        age = now - data["timestamp"] if data["timestamp"] else None
        return jsonify({
            "asset": asset,
            "price": data["price"],
            "currency": data["currency"],
            "age_seconds": round(age, 1) if age is not None else None,
        })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": time.time()})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
