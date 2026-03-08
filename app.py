from flask import Flask, jsonify
from flask_cors import CORS
import yfinance as yf
import requests

app = Flask(__name__)
CORS(app)

def get_eur_rate():
    try:
        r = requests.get('https://api.frankfurter.app/latest?from=USD&to=EUR', timeout=8)
        return r.json()['rates']['EUR']
    except:
        pass
    try:
        r = requests.get('https://open.er-api.com/v6/latest/USD', timeout=8)
        return r.json()['rates']['EUR']
    except:
        pass
    return 0.92

@app.route('/test')
def test():
    results = {}
    try:
        results['eur_rate'] = get_eur_rate()
    except Exception as e:
        results['eur_rate_error'] = str(e)
    try:
        btc = yf.Ticker("BTC-EUR")
        results['btc_yf'] = btc.fast_info['last_price']
    except Exception as e:
        results['btc_yf_error'] = str(e)
    try:
        gold = yf.Ticker("GC=F")
        results['gold_usd'] = gold.fast_info['last_price']
    except Exception as e:
        results['gold_error'] = str(e)
    try:
        silver = yf.Ticker("SI=F")
        results['silver_usd'] = silver.fast_info['last_price']
    except Exception as e:
        results['silver_error'] = str(e)
    try:
        r = requests.get('https://api.coinbase.com/v2/prices/BTC-EUR/spot', timeout=8)
        results['coinbase_btc'] = float(r.json()['data']['amount'])
    except Exception as e:
        results['coinbase_error'] = str(e)
    return jsonify(results)

@app.route('/prices')
def prices():
    result = {}
    eur = get_eur_rate()
    try:
        btc = yf.Ticker("BTC-EUR")
        result['btc'] = round(btc.fast_info['last_price'], 0)
    except:
        try:
            r = requests.get('https://api.coinbase.com/v2/prices/BTC-EUR/spot', timeout=8)
            result['btc'] = float(r.json()['data']['amount'])
        except:
            result['btc'] = None
    try:
        gold = yf.Ticker("GC=F")
        result['gold'] = round(gold.fast_info['last_price'] * eur, 2)
    except:
        result['gold'] = None
    try:
        silver = yf.Ticker("SI=F")
        result['silver'] = round(silver.fast_info['last_price'] * eur, 4)
    except:
        result['silver'] = None
    return jsonify(result)

@app.route('/')
def index():
    return 'Preisalarm Server laeuft - /prices fuer Kurse, /test fuer Diagnose'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
