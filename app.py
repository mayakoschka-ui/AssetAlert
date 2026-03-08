import osimport time
import threading
import logging
from typing import Optional
import requests
from flask import Flask, jsonify, render_template
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ── Cache ──
price_cache = {
    "gold": {"price": None, "timestamp": 0},
    "silver": {"price": None, "timestamp": 0},
    "bitcoin": {"price": None, "timestamp": 0},
}
eur_usd_cache = {"rate": None, "timestamp": 0} # 1 USD = ? EUR
cache_lock = threading.Lock()

SESS = requests.Session()
SESS.headers.update({"User-Agent": "AssetAlert/1.0"})


# ── Fetch helpers ──

def fetch_metals():
    # type: () -> Optional[dict]
    """metals.live — free, no key, returns oz prices in USD"""
    try:
        r = SESS.get("https://metals.live/api/v1/spot", timeout=10)
        r.raise_for_status()
        data = r.json()
        # response is a list of {gold: x, silver: x, ...} or dict
        if isinstance(data, list):
            for item in data:
                if "gold" in item or "silver" in item:
                    return item
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("metals.live error: %s", e)
    return None


def fetch_gold_silver_via_frankfurter():
    # type: () -> Optional[dict]
    """
    Fallback: use open exchange approach via stooq CSV for metals.
    stooq.com provides free CSV data for commodity symbols.
    """
    result = {}
    for asset, symbol in [("gold", "XAUUSD"), ("silver", "XAGUSD")]:
        try:
            url = "https://stooq.com/q/l/?s={}&f=sd2t2ohlcv&h&e=csv".format(symbol)
            r = SESS.get(url, timeout=10)
            r.raise_for_status()
            lines = r.text.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split(",")
                close = float(parts[6]) # Close column
                result[asset] = close
        except Exception as e:
            logger.warning("stooq %s error: %s", asset, e)
    return result if result else None


def fetch_bitcoin_coingecko():
    # type: () -> Optional[float]
    """CoinGecko free API — BTC price in USD"""
    try:
        r = SESS.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
            timeout=10
        )
        r.raise_for_status()
        return float(r.json()["bitcoin"]["usd"])
    except Exception as e:
        logger.warning("CoinGecko error: %s", e)
    return None


def fetch_bitcoin_binance():
    # type: () -> Optional[float]
    """Binance public API — BTC/USDT price (no key needed)"""
    try:
        r = SESS.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "BTCUSDT"},
            timeout=10
        )
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        logger.warning("Binance error: %s", e)
    return None


def fetch_eur_rate():
    # type: () -> Optional[float]
    """frankfurter.app — free ECB exchange rates, returns EUR/USD (1 EUR = ? USD)"""
    try:
        r = SESS.get(
            "https://api.frankfurter.app/latest",
            params={"from": "EUR", "to": "USD"},
            timeout=10
        )
        r.raise_for_status()
        eur_usd = float(r.json()["rates"]["USD"]) # 1 EUR = x USD
        return 1.0 / eur_usd # return: 1 USD = x EUR
    except Exception as e:
        logger.warning("Frankfurter EUR error: %s", e)
    return None


def fetch_eur_rate_fallback():
    # type: () -> Optional[float]
    """Fallback: exchangerate-api (free tier)"""
    try:
        r = SESS.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=10
        )
        r.raise_for_status()
        eur = float(r.json()["rates"]["EUR"]) # 1 USD = x EUR
        return eur
    except Exception as e:
        logger.warning("exchangerate-api error: %s", e)
    return None


# ── Background refresh ──

def refresh_cache():
    while True:
        # 1. EUR rate
        try:
            rate = fetch_eur_rate() or fetch_eur_rate_fallback()
            if rate:
                with cache_lock:
                    eur_usd_cache["rate"] = rate
                    eur_usd_cache["timestamp"] = time.time()
                logger.info("EUR rate: 1 USD = %.4f EUR", rate)
        except Exception as e:
            logger.error("EUR rate refresh error: %s", e)
        time.sleep(2)

        # 2. Gold + Silver via metals.live
        metals_ok = False
        try:
            metals = fetch_metals()
            if metals:
                gold_usd = metals.get("gold") or metals.get("XAU")
                silver_usd = metals.get("silver") or metals.get("XAG")
                if gold_usd:
                    with cache_lock:
                        price_cache["gold"]["price"] = float(gold_usd)
                        price_cache["gold"]["timestamp"] = time.time()
                    logger.info("Gold (metals.live): %.2f USD", gold_usd)
                    metals_ok = True
                if silver_usd:
                    with cache_lock:
                        price_cache["silver"]["price"] = float(silver_usd)
                        price_cache["silver"]["timestamp"] = time.time()
                    logger.info("Silver (metals.live): %.2f USD", silver_usd)
        except Exception as e:
            logger.error("metals.live refresh error: %s", e)
        time.sleep(2)

        # Fallback for gold/silver via stooq if metals.live failed
        if not metals_ok:
            try:
                stooq = fetch_gold_silver_via_frankfurter()
                if stooq:
                    for asset in ("gold", "silver"):
                        if asset in stooq:
                            with cache_lock:
                                price_cache[asset]["price"] = stooq[asset]
                                price_cache[asset]["timestamp"] = time.time()
                            logger.info("%s (stooq): %.2f USD", asset, stooq[asset])
            except Exception as e:
                logger.error("stooq fallback error: %s", e)
            time.sleep(2)

        # 3. Bitcoin
        try:
            btc = fetch_bitcoin_coingecko() or fetch_bitcoin_binance()
            if btc:
                with cache_lock:
                    price_cache["bitcoin"]["price"] = btc
                    price_cache["bitcoin"]["timestamp"] = time.time()
                logger.info("Bitcoin: %.2f USD", btc)
        except Exception as e:
            logger.error("Bitcoin refresh error: %s", e)

        time.sleep(40) # wait ~40s, total cycle ~50s


refresh_thread = threading.Thread(target=refresh_cache, daemon=True)
refresh_thread.start()


# ── Routes ──

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
                "age_seconds": round(age, 1) if age is not None else None,
                "stale": age is None or age > 180,
            }
        eur_rate = eur_usd_cache.get("rate")
        result["_eur_rate"] = round(eur_rate, 6) if eur_rate else None
    return jsonify(result)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": time.time()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
