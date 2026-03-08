from flask import Flask, jsonify
from flask_cors import CORS
import requests
import threading
import time

app = Flask(__name__)
CORS(app)

cache = {'gold': None, 'silver': None, 'btc': None}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def get_eur_rate():
    try:
        r = requests.get('https://api.frankfurter.app/latest?from=USD&to=EUR', 
                        timeout=8, headers=HEADERS)
        return r.json()['rates']['EUR']
    except:
        return 0.92

def fetch_yahoo(symbol):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d'
    r = requests.get(url, timeout=10, headers=HEADERS)
    data = r.json()
    price = data['chart']['result'][0]['meta']['regularMarketPrice']
    return float(price)

def fetch_prices():
    while True:
        try:
            eur = get_eur_rate()
            
            try:
                cache['btc'] = round(fetch_yahoo('BTC-EUR'), 0)
                print(f"BTC: {cache['btc']}")
            except Exception as e:
                print(f"BTC error: {e}")

            try:
                gold_usd = fetch_yahoo('GC=F')
                cache['gold'] = round(gold_usd * eur, 2)
                print(f"Gold: {cache['gold']}")
            except Exception as e:
                print(f"Gold error: {e}")

            try:
                silver_usd = fetch_yahoo('SI=F')
                cache['silver'] = round(silver_usd * eur, 4)
                print(f"Silver: {cache['silver']}")
            except Exception as e:
                print(f"Silver error: {e}")

        except Exception as e:
            print(f"General error: {e}")
        
        time.sleep(60)

# Background thread starten
t = threading.Thread(target=fetch_prices, daemon=True)
t.start()

@app.route('/')
def index():
    return 'Preisalarm Server laeuft'

@app.route('/prices')
def prices():
    return jsonify(cache)

@app.route('/test')
def test():
    eur = get_eur_rate()
    result = {'eur': eur, 'cache': cache}
    try:
        result['yahoo_btc_test'] = fetch_yahoo('BTC-EUR')
    except Exception as e:
        result['yahoo_btc_error'] = str(e)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
