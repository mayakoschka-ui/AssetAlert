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

# Primary and fallback symbols for each asset
SYMBOLS = {
    "gold":    ["GC=F", "MGC=F", "GOLD"],
    "silver":  ["SI=F", "SIL", "SIVR"],
    "bitcoin": ["BTC-USD"],
}

def fetch_price(asset: str) -> float | None:
    symbols = SYMBOLS.get(asset, [])
    for symbol in symbols:
        price = _try_fetch(symbol)
        if price is not None and price > 0:
            logger.info(f"  {asset} fetched via {symbol}: {price:.2f}")
            return price
        else:
            logger.warning(f"  {asset} symbol {symbol} returned no data, trying next...")
    logger.error(f"All symbols exhausted for {asset}")
    return None

def _try_fetch(symbol: str) -> float | None:
    """Try multiple yfinance methods to get a price."""
    try:
        ticker = yf.Ticker(symbol)

        # Method 1: fast_info.last_price (most reliable, no period issues)
        try:
            fi = ticker.fast_info
            price = getattr(fi, "last_price", None)
            if price and float(price) > 0:
                return float(price)
        except Exception as e:
            logger.debug(f"fast_info failed for {symbol}: {e}")

        # Method 2: history with 5d period (futures sometimes need wider window)
        try:
            data = ticker.history(period="5d", interval="1h")
            if not data.empty:
                return float(data["Close"].dropna().iloc[-1])
        except Exception as e:
            logger.debug(f"history 5d failed for {symbol}: {e}")

        # Method 3: history with 1mo period
        try:
            data = ticker.history(period="1mo", interval="1d")
            if not data.empty:
                return float(data["Close"].dropna().iloc[-1])
        except Exception as e:
            logger.debug(f"history 1mo failed for {symbol}: {e}")

        return None
    except Exception as e:
        logger.warning(f"_try_fetch error for {symbol}: {e}")
        return None

def refresh_cache():
    """Background thread: keep prices warm so /api/prices is instant."""
    while True:
        for asset in list(price_cache.keys()):
            try:
                price = fetch_price(asset)
                with cache_lock:
                    if price is not None:
                        price_cache[asset]["price"] = price
                        price_cache[asset]["timestamp"] = time.time()
                        logger.info(f"Cached {asset}: {price:.2f}")
                    else:
                        logger.warning(f"No price returned for {asset}, keeping last value")
            except Exception as e:
                logger.error(f"Cache refresh error for {asset}: {e}")
            time.sleep(4)  # stagger requests generously to avoid rate limits
        # Wait before next full cycle
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
