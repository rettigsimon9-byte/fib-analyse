from flask import Flask, render_template, request, jsonify, redirect
from analyse import analysiere, PERIODEN
from backtest import backtest_daytrade
from scanner import scan_tickers, DEFAULT_WATCHLIST, SCANNER_PERIODEN
from journal import (
    init_db, speichere_trade, pruefe_offene_trades,
    schliesse_trade, loesche_trade, lade_journal, lade_statistiken,
)

init_db()

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

BACKTEST_PERIODEN = [
    {'key': '5d',  'label': '5 Tage (15min)'},
    {'key': '1wk', 'label': '1 Woche (1h)'},
    {'key': '1mo', 'label': '1 Monat (1d)'},
    {'key': '3mo', 'label': '3 Monate (1d)'},
    {'key': '6mo', 'label': '6 Monate (1d)'},
    {'key': '1y',  'label': '1 Jahr (1d)'},
    {'key': '2y',  'label': '2 Jahre (1wk)'},
    {'key': '5y',  'label': '5 Jahre (1wk)'},
]


@app.route('/backtest')
def backtest_view():
    ticker  = request.args.get('ticker', '').strip().upper()
    periode = request.args.get('periode', '1y')

    if not ticker:
        return render_template('backtest.html',
            beliebte=BELIEBTE_TICKER,
            perioden=BACKTEST_PERIODEN,
            ergebnis=None,
            aktuelle_periode=periode,
        )

    ergebnis = backtest_daytrade(ticker, periode)
    return render_template('backtest.html',
        beliebte=BELIEBTE_TICKER,
        perioden=BACKTEST_PERIODEN,
        ergebnis=ergebnis,
        aktuelle_periode=periode,
        letzter_ticker=ticker,
    )


@app.route('/api/backtest')
def api_backtest():
    ticker  = request.args.get('ticker', '').strip().upper()
    periode = request.args.get('periode', '1y')
    if not ticker:
        return jsonify({'fehler': 'Ticker fehlt'})
    return jsonify(backtest_daytrade(ticker, periode))


@app.route('/api/analyse')
def api_analyse():
    ticker  = request.args.get('ticker', '').strip().upper()
    periode = request.args.get('periode', '1y')
    return jsonify(analysiere(ticker, periode))

# ── Journal ───────────────────────────────────────────────────────────────────

@app.route('/scanner')
def scanner_view():
    return render_template('scanner.html',
        default_watchlist=DEFAULT_WATCHLIST,
        scanner_perioden=SCANNER_PERIODEN,
    )

@app.route('/api/scanner', methods=['POST'])
def api_scanner():
    d       = request.get_json(force=True) or {}
    tickers = d.get('tickers', DEFAULT_WATCHLIST)
    periode = d.get('periode', '1d')
    return jsonify(scan_tickers(tickers, periode))

@app.route('/journal')
def journal_view():
    pruefe_offene_trades()
    trades = lade_journal()
    stats  = lade_statistiken()
    return render_template('journal.html', trades=trades, stats=stats)

@app.route('/api/journal/save', methods=['POST'])
def api_journal_save():
    d = request.get_json(force=True) or {}
    try:
        trade_id = speichere_trade(
            ticker      = d['ticker'],
            periode     = d.get('periode', '?'),
            richtung    = d['richtung'],
            einstieg    = float(d['einstieg']),
            take_profit = float(d['take_profit']),
            stop_loss   = float(d['stop_loss']),
            tp_pct      = float(d['tp_pct']),
            sl_pct      = float(d['sl_pct']),
            rr          = float(d['rr']),
            waehrung    = d.get('waehrung', 'EUR'),
        )
        return jsonify({'ok': True, 'id': trade_id})
    except Exception as e:
        return jsonify({'ok': False, 'fehler': str(e)}), 400

@app.route('/api/journal/check', methods=['POST'])
def api_journal_check():
    n = pruefe_offene_trades()
    return jsonify({'ok': True, 'aktualisiert': n})

@app.route('/api/journal/close', methods=['POST'])
def api_journal_close():
    d = request.get_json(force=True) or {}
    ok = schliesse_trade(
        trade_id   = int(d['id']),
        outcome    = d['outcome'],
        exit_preis = float(d['exit_preis']) if d.get('exit_preis') else None,
        notiz      = d.get('notiz', ''),
    )
    return jsonify({'ok': ok})

@app.route('/api/journal/delete', methods=['POST'])
def api_journal_delete():
    d = request.get_json(force=True) or {}
    loesche_trade(int(d['id']))
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
