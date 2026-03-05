from flask import Flask, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

@app.route('/prices')
def prices():
    result = {}

    # Bitcoin via Coinbase
    try:
        r = requests.get('https://api.coinbase.com/v2/prices/BTC-EUR/spot', timeout=5)
        result['btc'] = float(r.json()['data']['amount'])
    except:
        result['btc'] = None

    # Gold & Silver via stooq
    try:
        r = requests.get('https://stooq.com/q/l/?s=xaueur&f=l', timeout=5)
        result['gold'] = float(r.text.strip())
    except:
        result['gold'] = None

    try:
        r = requests.get('https://stooq.com/q/l/?s=xageur&f=l', timeout=5)
        result['silver'] = float(r.text.strip())
    except:
        result['silver'] = None

    return jsonify(result)

@app.route('/')
def index():
    return 'Preisalarm Server läuft ✓'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
