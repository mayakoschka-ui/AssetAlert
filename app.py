from flask import Flask, jsonify
from flask_cors import CORS
import yfinance as yf
import requests
import signal

app = Flask(__name__)
CORS(app)

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError()

def with_timeout(func, seconds=8):
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        result = func()
        signal.alarm(0)
        return result
    except TimeoutError:
        return None
    except Exception:
        signal.alarm(0)
        return None

def get_eur_rate():
    try:
        r = requests.get('https://api.frankfurter.app/latest?from=USD&to=EUR', timeout=6)
        return r.json()['rates']['EUR']
    except:
        return 0.92

@app.route('/prices')
def prices():
    result = {}
    eur = get_eur_rate()

    # Bitcoin
    def fetch_btc():
        btc = yf.Ticker("BTC-EUR")
        return round(btc.fast_info['last_price'], 0)

    def fetch_btc_fallback():
        r = requests.get('https://api.coinbase.com/v2/prices/BTC-EUR/spot', timeout=6)
        return float(r.json()['data']['amount'])

    result['btc'] = with_timeout(fetch_btc) or with_timeout(fetch_btc_fallback)

    # Gold
    def fetch_gold():
        gold = yf.Ticker("GC=F")
        return round(gold.fast_info['last_price'] * eur, 2)

    result['gold'] = with_timeout(fetch_gold)

    # Silver
    def fetch_silver():
        silver = yf.Ticker("SI=F")
        return round(silver.fast_info['last_price'] * eur, 4)

    result['silver'] = with_timeout(fetch_silver)

    return jsonify(result)

@app.route('/test')
def test():
    eur = get_eur_rate()
    results = {'eur_rate': eur}

    def fetch_btc():
        return yf.Ticker("BTC-EUR").fast_info['last_price']
    def fetch_gold():
        return yf.Ticker("GC=F").fast_info['last_price']
    def fetch_silver():
        return yf.Ticker("SI=F").fast_info['last_price']

    results['btc'] = with_timeout(fetch_btc)
    results['gold_usd'] = with_timeout(fetch_gold)
    results['silver_usd'] = with_timeout(fetch_silver)

    return jsonify(results)

@app.route('/')
def index():
    return 'Preisalarm Server laeuft'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
