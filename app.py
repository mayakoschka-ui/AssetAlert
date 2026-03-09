import os
import time
import threading
import logging
import requests
from flask import Flask, jsonify, render_template
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

cache = {
    "gold":    {"price": None, "ts": 0},
    "silver":  {"price": None, "ts": 0},
    "bitcoin": {"price": None, "ts": 0},
    "eur_rate": {"rate": None, "ts": 0},
}
lock = threading.Lock()

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "AssetAlert/2.0"


def safe_get(url, params=None, timeout=12):
    try:
        r = SESSION.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("GET %s failed: %s", url, exc)
        return None


def get_eur_rate():
    data = safe_get("https://api.frankfurter.app/latest",
                    params={"from": "EUR", "to": "USD"})
    if data and "rates" in data:
        return 1.0 / float(data["rates"]["USD"])
    data = safe_get("https://open.er-api.com/v6/latest/USD")
    if data and "rates" in data:
        return float(data["rates"]["EUR"])
    return None


def get_bitcoin():
    data = safe_get("https://api.binance.com/api/v3/ticker/price",
                    params={"symbol": "BTCUSDT"})
    if data and "price" in data:
        return float(data["price"])
    data = safe_get("https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": "bitcoin", "vs_currencies": "usd"})
    if data and "bitcoin" in data:
        return float(data["bitcoin"]["usd"])
    data = safe_get("https://api.kraken.com/0/public/Ticker",
                    params={"pair": "XBTUSD"})
    if data and "result" in data:
        try:
            pair = list(data["result"].values())[0]
            return float(pair["c"][0])
        except Exception:
            pass
    return None


def refresh_loop():
    while True:
        rate = get_eur_rate()
        if rate:
            with lock:
                cache["eur_rate"]["rate"] = rate
                cache["eur_rate"]["ts"] = time.time()
        btc = get_bitcoin()
        if btc:
            with lock:
                cache["bitcoin"]["price"] = btc
                cache["bitcoin"]["ts"] = time.time()
        time.sleep(50)


bg = threading.Thread(target=refresh_loop, daemon=True)
bg.start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/prices")
def api_prices():
    now = time.time()
    with lock:
        result = {}
        for asset in ("gold", "silver", "bitcoin"):
            d = cache[asset]
            age = now - d["ts"] if d["ts"] else None
            result[asset] = {
                "price": d["price"],
                "age": round(age, 1) if age else None,
                "stale": age is None or age > 180,
            }
        rate = cache["eur_rate"]["rate"]
        result["_eur_rate"] = round(rate, 6) if rate else None
    return jsonify(result)


@app.route("/api/metals")
def api_metals():
    gold = None
    silver = None
    try:
        r = SESSION.get("https://goldprice.today/api.php", timeout=10)
        d = r.json()
        gold = float(d["EUR"]["ounce"])
        silver = float(d["EUR"]["ounce"] / float(d["XAG"]["ounce"]
    except Exception as e:
        logger.warning("goldprice error: %s", e)
    return jsonify({"gold": gold, "silver": silver})

                                                 
@app.route("/health")
def health():
    return jsonify({"ok": True, "time": time.time()})

                                                 
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
