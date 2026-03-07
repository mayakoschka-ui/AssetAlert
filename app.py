from flask import Flask, jsonify
from flask_cors import CORS
import requests
import threading

app = Flask(__name__)
CORS(app)

# Cache für Preise
cache = {'gold': None, 'silver': None, 'btc': None, 'eur': 0.92}

def get_eur_rate():
    try:
        r = requests.get('https://api.frankfurter.app/latest?from=USD&to=EUR', timeout=6)
        return r.json()['rates']['EUR']
    except:
        return 0.92

def fetch_prices_background():
    try:
        import yfinance as yf
        eur = get_eur_rate()
        cache['eur'] = eur
        try:
            btc = yf.Ticker("BTC-EUR")
            cache['btc'] = round(btc.fast_info['last_price'], 0)
        except:
            pass
        try:
            gold = yf.Ticker("GC=F")
            cache['gold'] = round(gold.fast_info['last_price'] * eur, 2)
        except:
            pass
        try:
            silver = yf.Ticker("SI=F")
            cache['silver'] = round(silver.fast_info['last_price'] * eur, 4)
        except:
            pass
    except Exception as e:
        print(f"Background fetch error: {e}")
    # Alle 60 Sekunden wiederholen
    t = threading.Timer(60, fetch_prices_background)
    t.daemon = True
    t.start()

# Beim Start sofort im Hintergrund laden
t = threading.Timer(1, fetch_prices_background)
t.daemon = True
t.start()

@app.route('/')
def index():
    return 'Preisalarm Server laeuft'

@app.route('/prices')
def prices():
    return jsonify({
        'gold': cache['gold'],
        'silver': cache['silver'],
        'btc': cache['btc']
    })

@app.route('/test')
def test():
    return jsonify(cache)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
