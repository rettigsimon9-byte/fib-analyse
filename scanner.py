"""Ticker-Scanner: Scannt mehrere Ticker parallel auf aktive Daytrade-Signale.

Nutzt ThreadPoolExecutor damit alle Ticker gleichzeitig analysiert werden —
statt 20 × 3s = 60s dauert ein Scan nur ~4-6s.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from analyse import analysiere, PERIODEN

# Standard-Watchlist — alle Schnellzugriff-Ticker vom Dashboard
DEFAULT_WATCHLIST = [
    'AAPL', 'NVDA', 'MSFT', 'TSLA', 'AMZN',
    'BTC-USD', 'ETH-USD',
    'SAP.DE', 'SIE.DE', 'ALV.DE', 'VOW3.DE', 'DAX',
]

SCANNER_PERIODEN = [
    {'key': '1d',  'label': 'Intraday 5min'},
    {'key': '5d',  'label': 'Intraday 15min'},
    {'key': '1wk', 'label': 'Intraday 1h'},
    {'key': '1mo', 'label': 'Swing 1 Monat'},
]


def _scan_ticker(ticker: str, periode: str) -> dict:
    """Analysiert einen einzelnen Ticker. Läuft in einem Thread."""
    try:
        result = analysiere(ticker, periode, mit_chart=False)
        if result.get('fehler'):
            return {'ticker': ticker, 'fehler': result['fehler']}

        dt = result.get('daytrade', {})
        sig = result.get('signal', {})
        ind = result.get('indikatoren', {})

        return {
            'ticker':      ticker,
            'name':        result.get('name', ticker),
            'waehrung':    result.get('waehrung', ''),
            'aktuell':     result.get('aktuell', 0),
            'change_pct':  result.get('change_pct', 0),
            # Daytrade-Signal
            'richtung':    dt.get('richtung', ''),
            'kein_signal': dt.get('kein_signal', True),
            'staerke':     dt.get('staerke', 0),
            'rr':          dt.get('rr', 0),
            'einstieg':    dt.get('einstieg', 0),
            'stop_loss':   dt.get('stop_loss', 0),
            'take_profit': dt.get('take_profit', 0),
            'sl_pct':      dt.get('sl_pct', 0),
            'tp_pct':      dt.get('tp_pct', 0),
            'htf_trend':   dt.get('htf_trend', 'neutral'),
            'gruende':     dt.get('gruende', [])[:3],
            # Indikatoren
            'rsi':         ind.get('rsi', 0),
            'adx':         ind.get('adx', 0),
            'volumen_ratio': ind.get('volumen_ratio', 1.0),
            # Handelssignal (Swing)
            'signal_typ':  sig.get('typ', ''),
            'signal_text': sig.get('text', ''),
            'bullisch_pct': result.get('wahrscheinlichkeit_bullisch', 50),
            'fehler':      None,
        }
    except Exception as e:
        return {'ticker': ticker, 'fehler': str(e)}


def scan_tickers(tickers: list, periode: str = '1d', max_workers: int = 8) -> dict:
    """Scannt alle Ticker parallel. Gibt sortiertes Ergebnis zurück."""
    if not tickers:
        tickers = DEFAULT_WATCHLIST

    tickers = [t.strip().upper() for t in tickers if t.strip()]

    results = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tickers))) as ex:
        futures = {ex.submit(_scan_ticker, t, periode): t for t in tickers}
        for future in as_completed(futures):
            results.append(future.result())

    # Sortierung: aktive Signale zuerst, dann nach Stärke
    def _sort_key(r):
        if r.get('fehler'):
            return (3, 0)
        if not r.get('kein_signal'):
            staerke = r.get('staerke', 0)
            return (0, -staerke)
        return (2, 0)

    results.sort(key=_sort_key)

    long_signals  = [r for r in results if not r.get('kein_signal') and r.get('richtung') == 'LONG']
    short_signals = [r for r in results if not r.get('kein_signal') and r.get('richtung') == 'SHORT']
    kein_signal   = [r for r in results if r.get('kein_signal') and not r.get('fehler')]
    fehler        = [r for r in results if r.get('fehler')]

    return {
        'results':       results,
        'long_signals':  long_signals,
        'short_signals': short_signals,
        'kein_signal':   kein_signal,
        'fehler':        fehler,
        'n_total':       len(results),
        'n_long':        len(long_signals),
        'n_short':       len(short_signals),
        'periode':       periode,
        'periode_label': next((p['label'] for p in SCANNER_PERIODEN if p['key'] == periode), periode),
    }
