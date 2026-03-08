import osimport time
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
    'gold': {'price': None, 'ts': 0},
    'silver': {'price': None, 'ts': 0},
    'bitcoin': {'price': None, 'ts': 0},
    'eur_rate': {'rate': None, 'ts': 0},
}
lock = threading.Lock()

SESSION = requests.Session()
SESSION.headers['User-Agent'] = 'AssetAlert/2.0'


def safe_get(url, params=None, timeout=12):
    try:
        r = SESSION.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning('GET %s failed: %s', url, exc)
        return None


def get_eur_rate():
    # frankfurter.app - free ECB rates, no key
    data = safe_get('https://api.frankfurter.app/latest',
                    params={'from': 'EUR', 'to': 'USD'})
    if data and 'rates' in data:
        eur_per_usd = 1.0 / float(data['rates']['USD'])
        logger.info('EUR rate ok: %.4f', eur_per_usd)
        return eur_per_usd
    # fallback: open.er-api.com
    data = safe_get('https://open.er-api.com/v6/latest/USD')
    if data and 'rates' in data:
        return float(data['rates']['EUR'])
    return None


def get_gold_silver():
    # Primary: metals.live
    data = safe_get('https://metals.live/api/v1/spot')
    if data:
        if isinstance(data, list):
            for item in data:
                if 'gold' in item:
                    data = item
                    break
        if isinstance(data, dict):
            g = data.get('gold') or data.get('XAU')
            s = data.get('silver') or data.get('XAG')
            if g and s:
                logger.info('metals.live ok: gold=%.2f silver=%.2f', g, s)
                return float(g), float(s)
    # Fallback: gold-api.com (free, no key needed for spot)
    g_data = safe_get('https://www.goldapi.io/api/XAU/USD',
                      timeout=8)
    # goldapi needs a key - skip and try stooq
    # Fallback: stooq CSV
    gold = None
    silver = None
    for asset, sym in [('gold', 'xauusd'), ('silver', 'xagusd')]:
        try:
            r = SESSION.get(
                'https://stooq.com/q/l/?s={}&f=sd2t2ohlcv&h&e=csv'.format(sym),
                timeout=10)
            lines = r.text.strip().split('\n')
            if len(lines) >= 2:
                val = float(lines[1].split(',')[6])
                if asset == 'gold':
                    gold = val
                else:
                    silver = val
                logger.info('stooq %s ok: %.2f', asset, val)
        except Exception as e:
            logger.warning('stooq %s: %s', sym, e)
    return gold, silver


def get_bitcoin():
    # Primary: Binance public API (no key, very reliable)
    data = safe_get('https://api.binance.com/api/v3/ticker/price',
                    params={'symbol': 'BTCUSDT'})
    if data and 'price' in data:
        logger.info('Binance BTC ok: %.2f', float(data['price']))
        return float(data['price'])
    # Fallback: CoinGecko
    data = safe_get('https://api.coingecko.com/api/v3/simple/price',
                    params={'ids': 'bitcoin', 'vs_currencies': 'usd'})
    if data and 'bitcoin' in data:
        return float(data['bitcoin']['usd'])
    # Fallback: Kraken
    data = safe_get('https://api.kraken.com/0/public/Ticker',
                    params={'pair': 'XBTUSD'})
    if data and 'result' in data:
        try:
            pair = list(data['result'].values())[0]
            return float(pair['c'][0])
        except Exception:
            pass
    return None


def refresh_loop():
    while True:
        # EUR rate
        rate = get_eur_rate()
        if rate:
            with lock:
                cache['eur_rate']['rate'] = rate
                cache['eur_rate']['ts'] = time.time()

        # Gold + Silver
        gold, silver = get_gold_silver()
        with lock:
            if gold:
                cache['gold']['price'] = gold
                cache['gold']['ts'] = time.time()
            if silver:
                cache['silver']['price'] = silver
                cache['silver']['ts'] = time.time()

        # Bitcoin
        btc = get_bitcoin()
        if btc:
            with lock:
                cache['bitcoin']['price'] = btc
                cache['bitcoin']['ts'] = time.time()

        time.sleep(50)


# Start background thread AFTER app is defined
bg = threading.Thread(target=refresh_loop, daemon=True)
bg.start()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/prices')
def api_prices():
    now = time.time()
    with lock:
        result = {}
        for asset in ('gold', 'silver', 'bitcoin'):
            d = cache[asset]
            age = now - d['ts'] if d['ts'] else None
            result[asset] = {
                'price': d['price'],
                'age': round(age, 1) if age else None,
                'stale': age is None or age > 180,
            }
        rate = cache['eur_rate']['rate']
        result['_eur_rate'] = round(rate, 6) if rate else None
    return jsonify(result)


@app.route('/health')
def health():
    return jsonify({'ok': True, 'time': time.time()})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
