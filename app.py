import osimport time
import threading
import logging
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import yfinance as yf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

price_cache = {
"gold": {"price": None, "currency": "USD", "timestamp": 0},
"silver": {"price": None, "currency": "USD", "timestamp": 0},
"bitcoin": {"price": None, "currency": "USD", "timestamp": 0},
}
eur_usd_cache = {"rate": None, "timestamp": 0} # 1 EUR = ? USD
cache_lock = threading.Lock()

SYMBOLS = {
"gold": "GC=F",
"silver": "SI=F",
"bitcoin": "BTC-USD",
}
EUR_USD_SYMBOL = "EURUSD=X"

def fetch_ticker_price(symbol: str) -> float | None:
try:
ticker = yf.Ticker(symbol)
data = ticker.history(period="1d", interval="1m")
if data.empty:
info = ticker.fast_info
price = getattr(info, "last_price", None)
return float(price) if price else None
return float(data["Close"].iloc[-1])
except Exception as e:
logger.warning(f"Error fetching {symbol}: {e}")
return None

def refresh_cache():
while True:
# Fetch EUR/USD
try:
rate = fetch_ticker_price(EUR_USD_SYMBOL)
if rate:
with cache_lock:
eur_usd_cache["rate"] = rate
eur_usd_cache["timestamp"] = time.time()
logger.info(f"Cached EUR/USD: {rate:.4f}")
except Exception as e:
logger.error(f"EUR/USD cache error: {e}")
time.sleep(3)

# Fetch assets
for asset, symbol in SYMBOLS.items():
try:
price = fetch_ticker_price(symbol)
with cache_lock:
if price is not None:
price_cache[asset]["price"] = price
price_cache[asset]["timestamp"] = time.time()
logger.info(f"Cached {asset}: {price:.2f}")
except Exception as e:
logger.error(f"Cache error for {asset}: {e}")
time.sleep(3)

time.sleep(36) # ~50s total cycle

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
# _eur_rate: how many EUR per 1 USD (to convert USD price -> EUR)
eur_usd = eur_usd_cache.get("rate")
result["_eur_rate"] = round(1.0 / eur_usd, 6) if eur_usd else None
return jsonify(result)

@app.route("/health")
def health():
return jsonify({"status": "ok", "timestamp": time.time()})

if __name__ == "__main__":
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port, debug=False)
