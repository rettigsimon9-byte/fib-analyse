from flask import Flask, render_template, request, jsonify
from analyse import analysiere, PERIODEN

app = Flask(__name__)

BELIEBTE_TICKER = [
    {'symbol': 'AAPL',  'name': 'Apple'},
    {'symbol': 'NVDA',  'name': 'Nvidia'},
    {'symbol': 'MSFT',  'name': 'Microsoft'},
    {'symbol': 'TSLA',  'name': 'Tesla'},
    {'symbol': 'AMZN',  'name': 'Amazon'},
    {'symbol': 'BTC-USD','name': 'Bitcoin'},
    {'symbol': 'ETH-USD','name': 'Ethereum'},
    {'symbol': 'SAP.DE', 'name': 'SAP'},
    {'symbol': 'SIE.DE', 'name': 'Siemens'},
    {'symbol': 'ALV.DE', 'name': 'Allianz'},
    {'symbol': 'VOW3.DE','name': 'Volkswagen'},
    {'symbol': 'DAX',    'name': 'DAX (Index)'},
]

@app.route('/')
def index():
    return render_template('index.html',
        beliebte=BELIEBTE_TICKER,
        perioden=PERIODEN,
    )

@app.route('/analyse')
def analyse():
    ticker  = request.args.get('ticker', '').strip().upper()
    periode = request.args.get('periode', '1y')

    if not ticker:
        return render_template('index.html',
            beliebte=BELIEBTE_TICKER,
            perioden=PERIODEN,
            fehler='Bitte einen Ticker eingeben.'
        )

    ergebnis = analysiere(ticker, periode)

    if ergebnis.get('fehler'):
        return render_template('index.html',
            beliebte=BELIEBTE_TICKER,
            perioden=PERIODEN,
            fehler=ergebnis['fehler'],
            letzter_ticker=ticker,
        )

    return render_template('analyse.html',
        d=ergebnis,
        perioden=PERIODEN,
        aktuelle_periode=periode,
    )

@app.route('/api/analyse')
def api_analyse():
    ticker  = request.args.get('ticker', '').strip().upper()
    periode = request.args.get('periode', '1y')
    return jsonify(analysiere(ticker, periode))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
