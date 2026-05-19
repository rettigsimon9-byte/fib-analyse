from flask import Flask, render_template, request, jsonify, redirect
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

MULTI_PERIODEN = [
    {'key': '5d',  'label': '5 Tage'},
    {'key': '1mo', 'label': '1 Monat'},
    {'key': '6mo', 'label': '6 Monate'},
    {'key': '1y',  'label': '1 Jahr'},
]

@app.route('/multi')
def multi():
    ticker = request.args.get('ticker', '').strip().upper()
    if not ticker:
        return redirect('/')

    resultate = {}
    for p in MULTI_PERIODEN:
        try:
            resultate[p['key']] = analysiere(ticker, p['key'], mit_chart=False)
        except Exception as e:
            resultate[p['key']] = {'fehler': str(e)}

    # Erstes erfolgreiches Ergebnis für Name/Währung
    meta = next((r for r in resultate.values() if not r.get('fehler')), None)
    if not meta:
        return render_template('index.html',
            beliebte=BELIEBTE_TICKER,
            perioden=PERIODEN,
            fehler=f'Ticker "{ticker}" konnte nicht geladen werden.',
            letzter_ticker=ticker,
        )

    return render_template('multi.html',
        ticker=ticker,
        meta=meta,
        resultate=resultate,
        perioden_liste=MULTI_PERIODEN,
    )

@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    try:
        import requests as req
        r = req.get(
            'https://query1.finance.yahoo.com/v1/finance/search',
            params={'q': q, 'quotesCount': 7, 'newsCount': 0},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=4,
        )
        quotes = r.json().get('quotes', [])
        results = []
        for qt in quotes:
            symbol = qt.get('symbol', '')
            name = qt.get('longname') or qt.get('shortname') or symbol
            exch = qt.get('exchDisp', '')
            typ = qt.get('quoteType', '')
            if typ not in ('EQUITY', 'ETF', 'CRYPTOCURRENCY', 'INDEX', 'FUTURE'):
                continue
            results.append({'symbol': symbol, 'name': name, 'exchange': exch})
        return jsonify(results)
    except Exception:
        return jsonify([])

@app.route('/api/lookup')
def api_lookup():
    ticker = request.args.get('ticker', '').strip().upper()
    if not ticker:
        return jsonify({'name': None, 'currency': None})
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        name = tk.fast_info.long_name or ticker
        currency = tk.fast_info.currency or '?'
        return jsonify({'name': name, 'currency': currency})
    except Exception:
        return jsonify({'name': None, 'currency': None})

@app.route('/api/analyse')
def api_analyse():
    ticker  = request.args.get('ticker', '').strip().upper()
    periode = request.args.get('periode', '1y')
    return jsonify(analysiere(ticker, periode))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
