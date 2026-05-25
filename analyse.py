import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import time
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    _BERLIN = ZoneInfo('Europe/Berlin')
except Exception:
    _BERLIN = None

_fx_cache: dict = {}
_FX_TTL = 3600  # 1 Stunde


def _fmt_zeit(ts) -> str:
    """Formatiert einen Zeitstempel als 'TT.MM.JJJJ HH:MM' in Europa/Berlin."""
    try:
        if getattr(ts, 'tzinfo', None) is None:
            ts = ts.tz_localize('UTC') if hasattr(ts, 'tz_localize') else ts.replace(tzinfo=timezone.utc)
        if _BERLIN is not None:
            ts = ts.tz_convert(_BERLIN) if hasattr(ts, 'tz_convert') else ts.astimezone(_BERLIN)
        return ts.strftime('%d.%m.%Y %H:%M')
    except Exception:
        try:
            return ts.strftime('%d.%m.%Y %H:%M')
        except Exception:
            return str(ts)


def _jetzt_berlin() -> str:
    now = datetime.now(_BERLIN) if _BERLIN is not None else datetime.now()
    return now.strftime('%d.%m.%Y %H:%M')


def hole_eur_kurs(waehrung: str) -> float:
    if waehrung == 'EUR':
        return 1.0
    jetzt = time.time()
    if waehrung in _fx_cache:
        kurs, ts = _fx_cache[waehrung]
        if jetzt - ts < _FX_TTL:
            return kurs
    try:
        fx = yf.Ticker(f'{waehrung}EUR=X')
        kurs = fx.fast_info.last_price
        if kurs and kurs > 0:
            _fx_cache[waehrung] = (kurs, jetzt)
            return kurs
    except Exception:
        pass
    return 1.0

# ── Fibonacci-Konstanten ──────────────────────────────────────────────────────

FIB_RETRACEMENTS = {
    '0,0 %':    0.000,
    '23,6 %':   0.236,
    '38,2 %':   0.382,
    '50,0 %':   0.500,
    '61,8 %':   0.618,
    '76,4 %':   0.764,
    '100,0 %':  1.000,
}

FIB_EXTENSIONS = {
    '127,2 %':  1.272,
    '138,2 %':  1.382,
    '161,8 %':  1.618,
    '200,0 %':  2.000,
    '261,8 %':  2.618,
}

FIB_FARBEN = {
    '0,0 %':    '#ef4444',
    '23,6 %':   '#f97316',
    '38,2 %':   '#eab308',
    '50,0 %':   '#22c55e',
    '61,8 %':   '#3b82f6',
    '76,4 %':   '#8b5cf6',
    '100,0 %':  '#ef4444',
    '127,2 %':  '#06b6d4',
    '138,2 %':  '#0ea5e9',
    '161,8 %':  '#6366f1',
    '200,0 %':  '#ec4899',
    '261,8 %':  '#f43f5e',
}

PERIODEN = {
    '1d':   {'yf': '1d',  'interval': '5m',  'label': '1 Tag (5min)',   'fenster': 5, 'intraday': True},
    '5d':   {'yf': '5d',  'interval': '15m', 'label': '5 Tage (15min)', 'fenster': 5, 'intraday': True},
    '1wk':  {'yf': '5d',  'interval': '1h',  'label': '1 Woche (1h)',   'fenster': 4, 'intraday': True},
    '1mo':  {'yf': '1mo',  'interval': '1d',  'label': '1 Monat',       'fenster': 10, 'intraday': False},
    '3mo':  {'yf': '3mo',  'interval': '1d',  'label': '3 Monate',      'fenster': 10, 'intraday': False},
    '6mo':  {'yf': '6mo',  'interval': '1d',  'label': '6 Monate',      'fenster': 10, 'intraday': False},
    '1y':   {'yf': '1y',   'interval': '1d',  'label': '1 Jahr',        'fenster': 10, 'intraday': False},
    '2y':   {'yf': '2y',   'interval': '1wk', 'label': '2 Jahre',       'fenster': 8,  'intraday': False},
    '5y':   {'yf': '5y',   'interval': '1wk', 'label': '5 Jahre',       'fenster': 8,  'intraday': False},
}

# Größere Ersatz-Zeitfenster je Intraday-Intervall. yfinance liefert für
# period='1d'/5m am Wochenende, an Feiertagen oder vor Börsenstart oft keine
# oder zu wenige Kerzen – dann wird das nächstgrößere Fenster nachgeladen.
INTRADAY_FALLBACK = {
    '5m':  ['5d', '1mo'],
    '15m': ['1mo', '2mo'],
    '1h':  ['1mo', '3mo'],
}

WAEHRUNG_SYMBOLE = {
    'EUR': '€', 'USD': '$', 'GBP': '£', 'CHF': 'CHF',
    'JPY': '¥', 'CAD': 'CA$', 'AUD': 'A$', 'HKD': 'HK$',
    'CNY': '¥', 'SEK': 'kr', 'NOK': 'kr', 'DKK': 'kr',
}

KERZEN_DEFINITIONEN = {
    'hammer':               {'richtung': 'bullisch', 'text': 'Hammer – bullisches Umkehrsignal',            'score': +12},
    'inverted_hammer':      {'richtung': 'bullisch', 'text': 'Invertierter Hammer – mögliche Wende aufwärts','score': +8},
    'bullisches_engulfing': {'richtung': 'bullisch', 'text': 'Bullisches Engulfing – starkes Kaufsignal',    'score': +15},
    'morgenstern':          {'richtung': 'bullisch', 'text': 'Morgenstern – bullische Trendwende',            'score': +18},
    'bullischer_marubozu':  {'richtung': 'bullisch', 'text': 'Bullischer Marubozu – starkes Momentum',       'score': +10},
    'tweezer_bottom':       {'richtung': 'bullisch', 'text': 'Tweezer Bottom – Bodenbildung',                'score': +10},
    'shooting_star':        {'richtung': 'baerisch', 'text': 'Shooting Star – bärisches Umkehrsignal',       'score': -12},
    'hanging_man':          {'richtung': 'baerisch', 'text': 'Hanging Man – Trendumkehr-Warnung',            'score': -10},
    'baerisches_engulfing': {'richtung': 'baerisch', 'text': 'Bärisches Engulfing – starker Verkaufsdruck',  'score': -14},
    'abendstern':           {'richtung': 'baerisch', 'text': 'Abendstern – bärische Trendwende',             'score': -18},
    'baerischer_marubozu':  {'richtung': 'baerisch', 'text': 'Bärischer Marubozu – starker Abwärtsdruck',    'score': -10},
    'tweezer_top':          {'richtung': 'baerisch', 'text': 'Tweezer Top – Topbildung',                     'score': -10},
    'doji':                 {'richtung': 'neutral',  'text': 'Doji – Unentschlossenheit am Markt',           'score': 0},
    'spinning_top':         {'richtung': 'neutral',  'text': 'Spinning Top – Unentschlossenheit',            'score': 0},
}

CHARTMUSTER_DEFINITIONEN = {
    'double_bottom':           {'richtung': 'bullisch', 'text': 'Double Bottom (Doppelboden) – Umkehrsignal',                'score': +20},
    'double_top':              {'richtung': 'baerisch', 'text': 'Double Top (Doppeltop) – Umkehrsignal',                    'score': -20},
    'triple_bottom':           {'richtung': 'bullisch', 'text': 'Triple Bottom (Dreifachboden) – starkes Umkehrsignal',      'score': +24},
    'triple_top':              {'richtung': 'baerisch', 'text': 'Triple Top (Dreifachhoch) – starkes Umkehrsignal',         'score': -24},
    'head_shoulders':          {'richtung': 'baerisch', 'text': 'Kopf-Schulter-Formation – Trendumkehr abwärts',            'score': -22},
    'inv_head_shoulders':      {'richtung': 'bullisch', 'text': 'Invertierte K-S-Formation – Trendumkehr aufwärts',         'score': +22},
    'bull_flag':               {'richtung': 'bullisch', 'text': 'Bull Flag – Fortsetzung aufwärts',                         'score': +15},
    'bear_flag':               {'richtung': 'baerisch', 'text': 'Bear Flag – Fortsetzung abwärts',                         'score': -15},
    'bull_pennant':            {'richtung': 'bullisch', 'text': 'Bullischer Wimpel – Fortsetzung aufwärts',                 'score': +14},
    'bear_pennant':            {'richtung': 'baerisch', 'text': 'Bärischer Wimpel – Fortsetzung abwärts',                  'score': -14},
    'ascending_triangle':      {'richtung': 'bullisch', 'text': 'Aufsteigendes Dreieck – Ausbruch erwartet',               'score': +12},
    'descending_triangle':     {'richtung': 'baerisch', 'text': 'Absteigendes Dreieck – Ausbruch nach unten',              'score': -12},
    'symmetrical_triangle':    {'richtung': 'neutral',  'text': 'Symmetrisches Dreieck – Ausbruch in beide Richtungen',    'score':   0},
    'rising_wedge':            {'richtung': 'baerisch', 'text': 'Steigender Keil – bärisches Umkehrmuster',               'score': -14},
    'falling_wedge':           {'richtung': 'bullisch', 'text': 'Fallender Keil – bullisches Umkehrmuster',               'score': +14},
    'bull_expanding_triangle': {'richtung': 'bullisch', 'text': 'Bullisches Erweiterungsdreieck – Ausbruch aufwärts',      'score': +10},
    'bear_expanding_triangle': {'richtung': 'baerisch', 'text': 'Bärisches Erweiterungsdreieck – Ausbruch abwärts',       'score': -10},
}

# ── Datenabruf ────────────────────────────────────────────────────────────────

def lade_daten(ticker: str, periode: str = '1y'):
    cfg = PERIODEN.get(periode, PERIODEN['1y'])
    try:
        tk = yf.Ticker(ticker)

        # auto_adjust=False → echte Marktpreise, keine dividendenbereinigten Kurse
        df = tk.history(period=cfg['yf'], interval=cfg['interval'], auto_adjust=False)

        # MultiIndex bereinigen (tritt bei manchen yfinance-Versionen auf)
        if df is not None and isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Intraday-Fallback: leeres/zu kurzes Fenster mit größerem Zeitraum nachladen
        if cfg.get('intraday') and (df is None or df.empty or len(df) < 15):
            for fb in INTRADAY_FALLBACK.get(cfg['interval'], ['5d']):
                try:
                    df_fb = tk.history(period=fb, interval=cfg['interval'], auto_adjust=False)
                except Exception:
                    continue
                if df_fb is None or df_fb.empty:
                    continue
                if isinstance(df_fb.columns, pd.MultiIndex):
                    df_fb.columns = df_fb.columns.get_level_values(0)
                if len(df_fb) >= 15:
                    df = df_fb
                    break

        if df is None or df.empty:
            return None, None, 'USD', f'Kein Ticker "{ticker}" gefunden.'

        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col not in df.columns:
                return None, None, 'USD', f'Unvollständige Daten für "{ticker}".'

        # Währung ermitteln
        try:
            waehrung = tk.fast_info.currency or 'USD'
        except Exception:
            waehrung = 'USD'

        # Aktuellen Echtzeitkurs aus fast_info holen – schlägt historischen Close
        try:
            last_price = tk.fast_info.last_price
            if last_price and last_price > 0:
                df.loc[df.index[-1], 'Close'] = last_price
                df.loc[df.index[-1], 'High']  = max(df['High'].iloc[-1], last_price)
                df.loc[df.index[-1], 'Low']   = min(df['Low'].iloc[-1],  last_price)
        except Exception:
            pass

        try:
            name = tk.fast_info.long_name or ticker
        except Exception:
            name = ticker

        # Alle Kurse in EUR umrechnen
        fx_kurs = hole_eur_kurs(waehrung)
        if fx_kurs != 1.0:
            for col in ['Open', 'High', 'Low', 'Close']:
                df[col] = df[col] * fx_kurs
            waehrung = 'EUR'

        return df, name, waehrung, None
    except Exception as e:
        return None, None, 'USD', str(e)

# ── Swing-Erkennung ───────────────────────────────────────────────────────────

def erkenne_swings(df: pd.DataFrame, fenster: int = 10):
    highs, lows = [], []
    h = df['High'].values
    l = df['Low'].values
    idx = df.index

    for i in range(fenster, len(df) - fenster):
        if h[i] == max(h[i - fenster: i + fenster + 1]):
            highs.append((idx[i], h[i]))
        if l[i] == min(l[i - fenster: i + fenster + 1]):
            lows.append((idx[i], l[i]))

    return highs, lows

def markantester_swing(df: pd.DataFrame, fenster: int = 10):
    """Findet den signifikantesten Swing (größte Spanne) im Datensatz."""
    highs, lows = erkenne_swings(df, fenster)
    if not highs or not lows:
        return df['High'].max(), df['Low'].min(), 'aufwärts'

    # Letztes Hoch und letztes Tief
    letztes_hoch_ts, letztes_hoch_preis = highs[-1]
    letztes_tief_ts, letztes_tief_preis = lows[-1]

    # Richtung: Was kam zuletzt?
    if letztes_hoch_ts > letztes_tief_ts:
        # Hoch nach Tief → Aufwärtsbewegung; Fib misst den letzten Aufschwung
        # Suche das Tief VOR dem letzten Hoch
        tiefs_vor_hoch = [(ts, p) for ts, p in lows if ts < letztes_hoch_ts]
        if tiefs_vor_hoch:
            swing_tief_ts, swing_tief = tiefs_vor_hoch[-1]
        else:
            swing_tief = df['Low'].min()
        return letztes_hoch_preis, swing_tief, 'aufwärts'
    else:
        # Tief nach Hoch → Abwärtsbewegung
        hochs_vor_tief = [(ts, p) for ts, p in highs if ts < letztes_tief_ts]
        if hochs_vor_tief:
            swing_hoch_ts, swing_hoch = hochs_vor_tief[-1]
        else:
            swing_hoch = df['High'].max()
        return swing_hoch, letztes_tief_preis, 'abwärts'

# ── Fibonacci-Berechnung ──────────────────────────────────────────────────────

def berechne_fib_levels(hoch: float, tief: float, richtung: str):
    spanne = hoch - tief
    levels = {}

    if richtung == 'aufwärts':
        # Retracements: vom Hoch aus nach unten (mögliche Rücksetzer)
        for name, ratio in FIB_RETRACEMENTS.items():
            levels[name] = round(hoch - spanne * ratio, 4)
        # Extensions: über das Hoch hinaus (Kursziele)
        for name, ratio in FIB_EXTENSIONS.items():
            levels[name] = round(tief + spanne * ratio, 4)
    else:
        # Retracements: vom Tief aus nach oben (mögliche Erholungen)
        for name, ratio in FIB_RETRACEMENTS.items():
            levels[name] = round(tief + spanne * ratio, 4)
        # Extensions: unter das Tief (Abwärtsziele)
        for name, ratio in FIB_EXTENSIONS.items():
            levels[name] = round(hoch - spanne * ratio, 4)

    return levels

# ── Technische Indikatoren ────────────────────────────────────────────────────

def berechne_indikatoren(df: pd.DataFrame, intraday: bool = True,
                          ema200_override: float = None):
    close  = df['Close']
    high   = df['High']
    low    = df['Low']
    volume = df['Volume']
    indikatoren = {}

    # EMAs
    indikatoren['ema20']  = close.ewm(span=20,  adjust=False).mean().iloc[-1]
    indikatoren['ema50']  = close.ewm(span=50,  adjust=False).mean().iloc[-1]
    indikatoren['ema200'] = close.ewm(span=200, adjust=False).mean().iloc[-1]
    # Tagesbasierter EMA200 nur für Chart-Anzeige gespeichert, nicht für Scoring
    indikatoren['ema200_daily'] = ema200_override if ema200_override is not None else indikatoren['ema200']

    # RSI (14)
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(com=13, adjust=False).mean().iloc[-1]
    if avg_loss == 0:
        indikatoren['rsi'] = 100.0
    else:
        rs = avg_gain / avg_loss
        indikatoren['rsi'] = round(100 - (100 / (1 + rs)), 1)

    # MACD (12, 26, 9) + Histogramm Vorperiode für echtes Kreuz
    ema12       = close.ewm(span=12, adjust=False).mean()
    ema26       = close.ewm(span=26, adjust=False).mean()
    macd_line   = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist_serie  = macd_line - signal_line
    indikatoren['macd']           = macd_line.iloc[-1]
    indikatoren['macd_signal']    = signal_line.iloc[-1]
    indikatoren['macd_hist']      = hist_serie.iloc[-1]
    indikatoren['macd_hist_prev'] = hist_serie.iloc[-2] if len(hist_serie) > 1 else hist_serie.iloc[-1]

    # Volumen-Trend
    vol_avg   = volume.rolling(20).mean().iloc[-1]
    vol_letzt = volume.iloc[-1]
    indikatoren['volumen_ratio'] = vol_letzt / vol_avg if vol_avg > 0 else 1.0

    # ATR (14)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr_serie = tr.rolling(14).mean()
    indikatoren['atr'] = atr_serie.iloc[-1]

    # Stochastic Slow (14, 3, 3)
    stoch_h   = high.rolling(14).max()
    stoch_l   = low.rolling(14).min()
    stoch_raw = 100 * (close - stoch_l) / (stoch_h - stoch_l).replace(0, 1e-9)
    stoch_k   = stoch_raw.rolling(3).mean()   # geglättetes %K
    stoch_d   = stoch_k.rolling(3).mean()     # %D (Signallinie)
    indikatoren['stoch_k']      = round(stoch_k.iloc[-1],  1)
    indikatoren['stoch_d']      = round(stoch_d.iloc[-1],  1)
    indikatoren['stoch_k_prev'] = round(stoch_k.iloc[-2] if len(stoch_k) > 1 else stoch_k.iloc[-1], 1)

    # Bollinger Bands (20, 2σ)
    bb_mid   = close.rolling(20).mean()
    bb_std   = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_range = (bb_upper - bb_lower).iloc[-1]
    indikatoren['bb_upper']  = round(bb_upper.iloc[-1], 4)
    indikatoren['bb_lower']  = round(bb_lower.iloc[-1], 4)
    indikatoren['bb_mid']    = round(bb_mid.iloc[-1],   4)
    indikatoren['bb_pos']    = round((close.iloc[-1] - bb_lower.iloc[-1]) / bb_range, 3) if bb_range > 0 else 0.5
    indikatoren['bb_breite'] = round(bb_range / bb_mid.iloc[-1] * 100, 2) if bb_mid.iloc[-1] > 0 else 5.0

    # ADX (14) mit +DI / -DI
    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm_f  = plus_dm.where(plus_dm  > minus_dm, 0.0)
    minus_dm_f = minus_dm.where(minus_dm > plus_dm,  0.0)
    atr14    = atr_serie.replace(0, 1e-9)
    plus_di  = 100 * plus_dm_f.ewm(com=13,  adjust=False).mean() / atr14
    minus_di = 100 * minus_dm_f.ewm(com=13, adjust=False).mean() / atr14
    di_sum   = (plus_di + minus_di).replace(0, 1e-9)
    dx       = (plus_di - minus_di).abs() / di_sum * 100
    adx      = dx.ewm(com=13, adjust=False).mean()
    indikatoren['adx']      = round(adx.iloc[-1],      1)
    indikatoren['plus_di']  = round(plus_di.iloc[-1],  1)
    indikatoren['minus_di'] = round(minus_di.iloc[-1], 1)

    # VWAP (täglicher Reset) – nur für Intraday-Charts sinnvoll
    if intraday:
        typical = (high + low + close) / 3
        try:
            dates      = pd.Series(df.index.date, index=df.index)
            cum_tp_vol = (typical * volume).groupby(dates).cumsum()
            cum_vol    = volume.groupby(dates).cumsum().replace(0, 1)
            vwap_serie = cum_tp_vol / cum_vol
        except Exception:
            cum_tp_vol = (typical * volume).cumsum()
            cum_vol    = volume.cumsum().replace(0, 1)
            vwap_serie = cum_tp_vol / cum_vol
        indikatoren['vwap'] = round(vwap_serie.iloc[-1], 4)
    else:
        indikatoren['vwap'] = 0  # VWAP auf Daily/Weekly-Bars irreführend

    indikatoren['aktuell'] = close.iloc[-1]
    indikatoren['vortag']  = close.iloc[-2] if len(close) > 1 else close.iloc[-1]
    indikatoren['hoch52w'] = high.rolling(min(252, len(df))).max().iloc[-1]
    indikatoren['tief52w'] = low.rolling(min(252, len(df))).min().iloc[-1]

    return indikatoren

# ── Wahrscheinlichkeitsberechnung ─────────────────────────────────────────────

def berechne_wahrscheinlichkeit(aktuell: float, levels: dict,
                                 ind: dict, richtung: str):
    score = 50.0  # Neutraler Ausgangspunkt
    faktoren = []

    alle_preise = sorted(levels.values())

    # ── 1. Fibonacci-Positionsanalyse ────────────────────────────────────────
    supports    = [p for p in alle_preise if p < aktuell]
    resistances = [p for p in alle_preise if p > aktuell]

    naechster_support    = max(supports)    if supports    else None
    naechste_resistance  = min(resistances) if resistances else None

    if naechster_support:
        abstand_pct = (aktuell - naechster_support) / aktuell * 100
        # Je näher am Support → bullisher
        if abstand_pct < 0.5:
            score += 18
            faktoren.append({'text': f'Preis direkt auf Fib-Support ({naechster_support:.2f})', 'wert': '+18', 'farbe': 'success'})
        elif abstand_pct < 1.5:
            score += 12
            faktoren.append({'text': f'Preis nahe Fib-Support ({naechster_support:.2f}, {abstand_pct:.1f}% entfernt)', 'wert': '+12', 'farbe': 'success'})
        elif abstand_pct < 3.0:
            score += 6
            faktoren.append({'text': f'Fib-Support in Reichweite ({naechster_support:.2f})', 'wert': '+6', 'farbe': 'success'})

    if naechste_resistance:
        abstand_pct = (naechste_resistance - aktuell) / aktuell * 100
        # Je näher an Resistance → bärischer
        if abstand_pct < 0.5:
            score -= 15
            faktoren.append({'text': f'Preis direkt unter Fib-Widerstand ({naechste_resistance:.2f})', 'wert': '−15', 'farbe': 'danger'})
        elif abstand_pct < 1.5:
            score -= 8
            faktoren.append({'text': f'Fib-Widerstand knapp über Preis ({naechste_resistance:.2f})', 'wert': '−8', 'farbe': 'danger'})

    # Goldene Zone (38.2% – 61.8%) — stärkste Support/Resistance
    golden_levels = [p for name, p in levels.items() if '38,2' in name or '61,8' in name]
    if golden_levels:
        for gl in golden_levels:
            if abs(aktuell - gl) / aktuell < 0.015:
                score += 10 if gl < aktuell else -10
                lbl = 'Goldene Zone Support' if gl < aktuell else 'Goldene Zone Widerstand'
                faktoren.append({'text': lbl, 'wert': '±10', 'farbe': 'warning'})

    # ── 2. Trend-Analyse (EMA) ────────────────────────────────────────────────
    ema20  = ind['ema20']
    ema50  = ind['ema50']
    ema200 = ind['ema200']

    if aktuell > ema20 > ema50 > ema200:
        score += 15
        faktoren.append({'text': 'Starker Aufwärtstrend (Preis > EMA20 > EMA50 > EMA200)', 'wert': '+15', 'farbe': 'success'})
    elif aktuell > ema20 > ema50:
        score += 10
        faktoren.append({'text': 'Aufwärtstrend (Preis > EMA20 > EMA50)', 'wert': '+10', 'farbe': 'success'})
    elif aktuell > ema200:
        score += 5
        faktoren.append({'text': 'Über 200-EMA (langfristig bullisch)', 'wert': '+5', 'farbe': 'success'})
    elif aktuell < ema20 < ema50 < ema200:
        score -= 15
        faktoren.append({'text': 'Starker Abwärtstrend (Preis < EMA20 < EMA50 < EMA200)', 'wert': '−15', 'farbe': 'danger'})
    elif aktuell < ema20 < ema50:
        score -= 10
        faktoren.append({'text': 'Abwärtstrend (Preis < EMA20 < EMA50)', 'wert': '−10', 'farbe': 'danger'})
    elif aktuell < ema200:
        score -= 5
        faktoren.append({'text': 'Unter 200-EMA (langfristig bärisch)', 'wert': '−5', 'farbe': 'danger'})

    # ── 3. RSI-Analyse (korrigiert: 45–65 neutral, nicht negativ) ───────────────
    rsi = ind['rsi']
    if rsi < 25:
        score += 20
        faktoren.append({'text': f'RSI stark überverkauft ({rsi:.0f}) – Bounce wahrscheinlich', 'wert': '+20', 'farbe': 'success'})
    elif rsi < 35:
        score += 12
        faktoren.append({'text': f'RSI überverkauft ({rsi:.0f})', 'wert': '+12', 'farbe': 'success'})
    elif rsi < 45:
        score += 4
        faktoren.append({'text': f'RSI leicht überverkauft ({rsi:.0f})', 'wert': '+4', 'farbe': 'secondary'})
    elif rsi <= 65:
        pass  # Neutralzone 45–65: kein Abzug
    elif rsi <= 75:
        score -= 4
        faktoren.append({'text': f'RSI leicht überkauft ({rsi:.0f})', 'wert': '−4', 'farbe': 'secondary'})
    else:
        score -= 20
        faktoren.append({'text': f'RSI stark überkauft ({rsi:.0f}) – Rücksetzer wahrscheinlich', 'wert': '−20', 'farbe': 'danger'})

    # ── 4. MACD (echtes Kreuz) ────────────────────────────────────────────────
    hist      = ind['macd_hist']
    hist_prev = ind.get('macd_hist_prev', hist)
    macd      = ind['macd']
    sig       = ind['macd_signal']
    if hist > 0 and hist_prev <= 0:
        score += 12
        faktoren.append({'text': 'Frisches MACD-Kaufkreuz', 'wert': '+12', 'farbe': 'success'})
    elif macd > sig and hist > 0:
        score += 8
        faktoren.append({'text': 'MACD bullisches Momentum', 'wert': '+8', 'farbe': 'success'})
    elif hist < 0 and hist_prev >= 0:
        score -= 12
        faktoren.append({'text': 'Frisches MACD-Verkaufskreuz', 'wert': '−12', 'farbe': 'danger'})
    elif macd < sig and hist < 0:
        score -= 8
        faktoren.append({'text': 'MACD bärisches Momentum', 'wert': '−8', 'farbe': 'danger'})

    # ── 5. Fibonacci-Richtungs-Bonus ─────────────────────────────────────────
    if richtung == 'aufwärts':
        score += 5
        faktoren.append({'text': 'Primärer Aufwärtstrend im Swing', 'wert': '+5', 'farbe': 'success'})
    else:
        score -= 5
        faktoren.append({'text': 'Primärer Abwärtstrend im Swing', 'wert': '−5', 'farbe': 'danger'})

    # ── 6. Volumen-Bestätigung ────────────────────────────────────────────────
    vr = ind['volumen_ratio']
    if vr > 1.5:
        faktoren.append({'text': f'Hohes Volumen ({vr:.1f}x Durchschnitt) – bestätigt Bewegung', 'wert': '±0', 'farbe': 'info'})

    # ── 7. VWAP ──────────────────────────────────────────────────────────────
    vwap = ind.get('vwap', 0)
    if vwap > 0:
        if aktuell > vwap * 1.003:
            score += 8
            faktoren.append({'text': f'Über VWAP ({vwap:.2f}) – institutionell bullisch', 'wert': '+8', 'farbe': 'success'})
        elif aktuell < vwap * 0.997:
            score -= 8
            faktoren.append({'text': f'Unter VWAP ({vwap:.2f}) – institutionell bärisch', 'wert': '−8', 'farbe': 'danger'})

    # ── 8. ADX – Trend-Stärke ────────────────────────────────────────────────
    adx      = ind.get('adx', 0)
    plus_di  = ind.get('plus_di', 0)
    minus_di = ind.get('minus_di', 0)
    if adx > 25:
        if plus_di > minus_di:
            score += 8
            faktoren.append({'text': f'ADX {adx:.0f} – starker Aufwärtstrend bestätigt', 'wert': '+8', 'farbe': 'success'})
        else:
            score -= 8
            faktoren.append({'text': f'ADX {adx:.0f} – starker Abwärtstrend bestätigt', 'wert': '−8', 'farbe': 'danger'})
    elif adx < 15:
        faktoren.append({'text': f'ADX {adx:.0f} – Range-Markt, Trend-Signale unzuverlässig', 'wert': '±0', 'farbe': 'secondary'})

    # ── 9. Bollinger Bands ────────────────────────────────────────────────────
    bb_pos    = ind.get('bb_pos', 0.5)
    bb_breite = ind.get('bb_breite', 5.0)
    if bb_pos <= 0.1:
        score += 10
        faktoren.append({'text': 'Preis am unteren Bollinger Band – überverkaufte Zone', 'wert': '+10', 'farbe': 'success'})
    elif bb_pos >= 0.9:
        score -= 10
        faktoren.append({'text': 'Preis am oberen Bollinger Band – überkaufte Zone', 'wert': '−10', 'farbe': 'danger'})
    if bb_breite < 2.0:
        faktoren.append({'text': f'BB-Squeeze ({bb_breite:.1f}%) – starke Bewegung steht bevor', 'wert': '±0', 'farbe': 'warning'})

    # ── 10. 52-Wochen-Hoch/Tief ──────────────────────────────────────────────
    h52 = ind.get('hoch52w', 0)
    t52 = ind.get('tief52w', 0)
    if h52 > 0 and aktuell > 0:
        abst_h52 = (h52 - aktuell) / aktuell * 100
        if aktuell >= h52 * 0.999:
            score += 8
            faktoren.append({'text': f'Neues 52-Wochen-Hoch ({aktuell:.2f}) – bullischer Ausbruch', 'wert': '+8', 'farbe': 'success'})
        elif abst_h52 < 2.0:
            score -= 8
            faktoren.append({'text': f'Nahe 52-Wochen-Hoch ({h52:.2f}) – starker Widerstand', 'wert': '−8', 'farbe': 'danger'})
    if t52 > 0 and aktuell > 0:
        abst_t52 = (aktuell - t52) / aktuell * 100
        if abst_t52 < 3.0:
            score += 8
            faktoren.append({'text': f'Nahe 52-Wochen-Tief ({t52:.2f}) – potentieller Boden', 'wert': '+8', 'farbe': 'success'})

    # ── 11. Stochastic ───────────────────────────────────────────────────────
    sk   = ind.get('stoch_k', 50)
    sk_p = ind.get('stoch_k_prev', sk)
    if sk < 20:
        if sk > sk_p:
            score += 10
            faktoren.append({'text': f'Stochastic dreht aufwärts aus überverkaufter Zone ({sk:.0f})', 'wert': '+10', 'farbe': 'success'})
        else:
            score += 5
            faktoren.append({'text': f'Stochastic überverkauft ({sk:.0f})', 'wert': '+5', 'farbe': 'secondary'})
    elif sk > 80:
        if sk < sk_p:
            score -= 10
            faktoren.append({'text': f'Stochastic dreht abwärts aus überkaufter Zone ({sk:.0f})', 'wert': '−10', 'farbe': 'danger'})
        else:
            score -= 5
            faktoren.append({'text': f'Stochastic überkauft ({sk:.0f})', 'wert': '−5', 'farbe': 'secondary'})

    score = max(5.0, min(95.0, score))

    return round(score, 1), faktoren, naechster_support, naechste_resistance

# ── Support/Resistance-Zonen (Cluster-Analyse) ───────────────────────────────

def berechne_zonen(levels: dict, toleranz_pct: float = 0.5):
    """Fasst eng beieinanderliegende Fibonacci-Levels zu Zonen zusammen."""
    sortiert = sorted(levels.items(), key=lambda x: x[1])
    zonen = []
    aktuelle_zone = []

    for name, preis in sortiert:
        if not aktuelle_zone:
            aktuelle_zone.append((name, preis))
        else:
            ref = aktuelle_zone[0][1]
            if abs(preis - ref) / ref * 100 <= toleranz_pct:
                aktuelle_zone.append((name, preis))
            else:
                if len(aktuelle_zone) > 1:
                    zonen.append({
                        'levels':  [n for n, _ in aktuelle_zone],
                        'preis_min': min(p for _, p in aktuelle_zone),
                        'preis_max': max(p for _, p in aktuelle_zone),
                        'preis_mitte': round(np.mean([p for _, p in aktuelle_zone]), 4),
                        'staerke':  len(aktuelle_zone),
                    })
                aktuelle_zone = [(name, preis)]

    if len(aktuelle_zone) > 1:
        zonen.append({
            'levels':  [n for n, _ in aktuelle_zone],
            'preis_min': min(p for _, p in aktuelle_zone),
            'preis_max': max(p for _, p in aktuelle_zone),
            'preis_mitte': round(np.mean([p for _, p in aktuelle_zone]), 4),
            'staerke':  len(aktuelle_zone),
        })

    return sorted(zonen, key=lambda z: z['preis_mitte'])

# ── Plotly-Chart ──────────────────────────────────────────────────────────────

def erstelle_chart(df: pd.DataFrame, levels: dict, zonen: list,
                   hoch: float, tief: float, richtung: str, ticker: str,
                   intraday: bool = False, ema200_daily: float = None,
                   kerzen_muster: list = None, chart_muster: list = None):

    # ── Indikatoren berechnen für Subcharts ──────────────────────────────────
    close = df['Close']

    # RSI-Serie
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, 1e-9)
    rsi_serie = 100 - (100 / (1 + rs))

    # MACD-Serie
    ema12       = close.ewm(span=12, adjust=False).mean()
    ema26       = close.ewm(span=26, adjust=False).mean()
    macd_line   = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram   = macd_line - signal_line

    # ── Stochastic-Serie für Chart ────────────────────────────────────────────
    stoch_h_c   = df['High'].rolling(14).max()
    stoch_l_c   = df['Low'].rolling(14).min()
    stoch_raw_c = 100 * (close - stoch_l_c) / (stoch_h_c - stoch_l_c).replace(0, 1e-9)
    stoch_k_c   = stoch_raw_c.rolling(3).mean()
    stoch_d_c   = stoch_k_c.rolling(3).mean()

    # ── Subplots anlegen ─────────────────────────────────────────────────────
    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.48, 0.13, 0.13, 0.13, 0.13],
    )

    # ── Bollinger Bands berechnen ────────────────────────────────────────────
    bb_mid_s   = close.rolling(20).mean()
    bb_std_s   = close.rolling(20).std()
    bb_upper_s = bb_mid_s + 2 * bb_std_s
    bb_lower_s = bb_mid_s - 2 * bb_std_s

    # ── VWAP berechnen ───────────────────────────────────────────────────────
    typical = (df['High'] + df['Low'] + close) / 3
    try:
        dates      = pd.Series(df.index.date, index=df.index)
        cum_tp_vol = (typical * df['Volume']).groupby(dates).cumsum()
        cum_vol    = df['Volume'].groupby(dates).cumsum().replace(0, 1)
        vwap_s     = cum_tp_vol / cum_vol
    except Exception:
        vwap_s = (typical * df['Volume']).cumsum() / df['Volume'].cumsum().replace(0, 1)

    # ── Row 1: Bollinger Bands (unter Candlestick zeichnen) ──────────────────
    fig.add_trace(go.Scatter(
        x=df.index, y=bb_upper_s,
        line=dict(color='rgba(99,102,241,0.5)', width=1),
        name='BB Oberes Band', showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=bb_lower_s,
        line=dict(color='rgba(99,102,241,0.5)', width=1),
        fill='tonexty', fillcolor='rgba(99,102,241,0.06)',
        name='BB Unteres Band', showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=bb_mid_s,
        line=dict(color='rgba(99,102,241,0.35)', width=0.8, dash='dot'),
        name='BB Mitte', showlegend=False,
    ), row=1, col=1)

    # ── Row 1: Candlestick ───────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'], high=df['High'],
        low=df['Low'],   close=df['Close'],
        name=ticker,
        increasing_line_color='#22c55e',
        decreasing_line_color='#ef4444',
        increasing_fillcolor='#22c55e',
        decreasing_fillcolor='#ef4444',
    ), row=1, col=1)

    # ── VWAP-Linie ───────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=df.index, y=vwap_s,
        line=dict(color='#f59e0b', width=1.8, dash='dot'),
        name='VWAP', showlegend=False,
    ), row=1, col=1)

    # ── Täglicher EMA200 (nur auf Intraday-Charts als Referenz) ──────────────
    if intraday and ema200_daily is not None:
        fig.add_hline(
            y=ema200_daily, row=1, col=1,
            line=dict(color='rgba(251,191,36,0.7)', width=1.2, dash='dashdot'),
            annotation_text=f'  EMA200d {ema200_daily:.2f}',
            annotation_position='right',
            annotation_font=dict(size=9, color='#fbbf24'),
        )

    # Fibonacci-Levels — Label nur zeigen wenn genug Abstand zum letzten Label
    sorted_levels     = sorted(levels.items(), key=lambda x: x[1])
    preis_range       = df['High'].max() - df['Low'].min()
    min_abstand       = preis_range * 0.035  # mind. 3.5% der sichtbaren Range
    letzter_label_preis = None

    for name, preis in sorted_levels:
        farbe = FIB_FARBEN.get(name, '#888888')
        ist_extension = any(x in name for x in ['127', '138', '161', '200', '261'])

        # Label nur wenn genug Abstand zum vorherigen Label
        zeige_label = (letzter_label_preis is None or
                       abs(preis - letzter_label_preis) >= min_abstand)

        fig.add_hline(
            y=preis, row=1, col=1,
            line=dict(color=farbe,
                      width=1.2 if not ist_extension else 0.8,
                      dash='solid' if not ist_extension else 'dash'),
            annotation_text=f'{name}  {preis:.2f}' if zeige_label else '',
            annotation_position='right',
            annotation_font=dict(size=9, color=farbe),
        )
        if zeige_label:
            letzter_label_preis = preis

    # Swing-Hoch / Tief
    fig.add_hline(y=hoch, row=1, col=1,
                  line=dict(color='#dc2626', width=1.5, dash='dot'),
                  annotation_text=f'  Swing-Hoch {hoch:.2f}',
                  annotation_position='right',
                  annotation_font=dict(size=9, color='#dc2626'))
    fig.add_hline(y=tief, row=1, col=1,
                  line=dict(color='#16a34a', width=1.5, dash='dot'),
                  annotation_text=f'  Swing-Tief {tief:.2f}',
                  annotation_position='right',
                  annotation_font=dict(size=9, color='#16a34a'))

    # Confluence-Zonen
    for zone in zonen:
        if zone['staerke'] >= 2:
            fig.add_hrect(
                y0=zone['preis_min'] * 0.999,
                y1=zone['preis_max'] * 1.001,
                fillcolor='rgba(59,130,246,0.08)',
                line_width=0,
                row=1, col=1,
            )

    # ── Row 2: Volumen ───────────────────────────────────────────────────────
    vol_farben = ['#22c55e' if c >= o else '#ef4444'
                  for c, o in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(
        x=df.index, y=df['Volume'],
        marker_color=vol_farben,
        name='Volumen',
        showlegend=False,
    ), row=2, col=1)

    # ── Row 3: RSI ───────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=df.index, y=rsi_serie,
        line=dict(color='#a78bfa', width=1.5),
        name='RSI',
        showlegend=False,
    ), row=3, col=1)
    fig.add_hline(y=70, row=3, col=1,
                  line=dict(color='#ef4444', width=0.8, dash='dot'),
                  annotation_text='  70', annotation_position='right',
                  annotation_font=dict(size=8, color='#ef4444'))
    fig.add_hline(y=30, row=3, col=1,
                  line=dict(color='#22c55e', width=0.8, dash='dot'),
                  annotation_text='  30', annotation_position='right',
                  annotation_font=dict(size=8, color='#22c55e'))
    fig.add_hline(y=50, row=3, col=1,
                  line=dict(color='#475569', width=0.5, dash='dot'))

    # ── Row 4: MACD ──────────────────────────────────────────────────────────
    hist_farben = ['#22c55e' if v >= 0 else '#ef4444' for v in histogram]
    fig.add_trace(go.Bar(
        x=df.index, y=histogram,
        marker_color=hist_farben,
        name='Histogramm',
        showlegend=False,
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=macd_line,
        line=dict(color='#3b82f6', width=1.2),
        name='MACD',
        showlegend=False,
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=signal_line,
        line=dict(color='#f97316', width=1.2),
        name='Signal',
        showlegend=False,
    ), row=4, col=1)
    fig.add_hline(y=0, row=4, col=1,
                  line=dict(color='#475569', width=0.5))

    # ── Row 5: Stochastic ────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=df.index, y=stoch_k_c,
        line=dict(color='#f59e0b', width=1.3),
        name='Stoch %K', showlegend=False,
    ), row=5, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=stoch_d_c,
        line=dict(color='#94a3b8', width=1.0, dash='dot'),
        name='Stoch %D', showlegend=False,
    ), row=5, col=1)
    fig.add_hline(y=80, row=5, col=1,
                  line=dict(color='#ef4444', width=0.8, dash='dot'),
                  annotation_text='  80', annotation_position='right',
                  annotation_font=dict(size=8, color='#ef4444'))
    fig.add_hline(y=20, row=5, col=1,
                  line=dict(color='#22c55e', width=0.8, dash='dot'),
                  annotation_text='  20', annotation_position='right',
                  annotation_font=dict(size=8, color='#22c55e'))
    fig.add_hline(y=50, row=5, col=1,
                  line=dict(color='#475569', width=0.5, dash='dot'))

    # ── Layout ───────────────────────────────────────────────────────────────
    rangebreaks = (
        [dict(bounds=['sat', 'mon']), dict(bounds=[20, 4], pattern='hour')]
        if intraday else
        [dict(bounds=['sat', 'mon'])]
    )

    axis_style = dict(gridcolor='#1e293b', showgrid=True, rangebreaks=rangebreaks)

    fig.update_layout(
        paper_bgcolor='#0f172a',
        plot_bgcolor='#0f172a',
        font=dict(color='#94a3b8', size=10),
        margin=dict(l=10, r=200, t=30, b=10),
        height=850,
        showlegend=False,
        barmode='relative',
        xaxis =dict(**axis_style, rangeslider_visible=False),
        xaxis2=dict(**axis_style),
        xaxis3=dict(**axis_style),
        xaxis4=dict(**axis_style),
        xaxis5=dict(**axis_style),
        yaxis =dict(gridcolor='#1e293b', showgrid=True, side='right'),
        yaxis2=dict(gridcolor='#1e293b', showgrid=True, side='right',
                    title=dict(text='Vol', font=dict(size=9, color='#64748b'))),
        yaxis3=dict(gridcolor='#1e293b', showgrid=True, side='right',
                    range=[0, 100],
                    title=dict(text='RSI', font=dict(size=9, color='#a78bfa'))),
        yaxis4=dict(gridcolor='#1e293b', showgrid=True, side='right',
                    title=dict(text='MACD', font=dict(size=9, color='#3b82f6'))),
        yaxis5=dict(gridcolor='#1e293b', showgrid=True, side='right',
                    range=[0, 100],
                    title=dict(text='Stoch', font=dict(size=9, color='#f59e0b'))),
    )

    # ── Muster-Annotationen im Chart ─────────────────────────────────────────
    alle_muster = (kerzen_muster or []) + (chart_muster or [])
    if alle_muster:
        x_last     = df.index[-1]
        last_high  = float(df.iloc[-1]['High'])
        last_low   = float(df.iloc[-1]['Low'])
        preis_span = hoch - tief if hoch != tief else last_high * 0.01

        bull_m = [m for m in alle_muster if m.get('richtung') == 'bullisch']
        bear_m = [m for m in alle_muster if m.get('richtung') == 'baerisch']
        neut_m = [m for m in alle_muster if m.get('richtung') not in ('bullisch', 'baerisch')]

        for gruppe, y_base, ay, farbe in [
            (bull_m, last_low  - preis_span * 0.04,  50, '#22c55e'),
            (bear_m, last_high + preis_span * 0.04, -50, '#ef4444'),
            (neut_m, last_high + preis_span * 0.02, -40, '#94a3b8'),
        ]:
            if not gruppe:
                continue
            label = ' · '.join(m['text'] for m in gruppe[:2])
            fig.add_annotation(
                x=x_last, y=y_base, xref='x', yref='y',
                text=f'📍 {label}',
                showarrow=True, arrowhead=2, arrowsize=1,
                arrowcolor=farbe, arrowwidth=1.5,
                ax=0, ay=ay,
                font=dict(size=9, color=farbe),
                bgcolor='rgba(15,23,42,0.88)',
                bordercolor=farbe, borderwidth=1, borderpad=3,
            )

        # Vertikale gepunktete Linie an der Muster-Kerze
        fig.add_vline(
            x=x_last,
            line=dict(color='rgba(251,191,36,0.35)', width=1, dash='dot'),
        )

    return fig.to_json()

# ── RSI-Divergenz Erkennung ───────────────────────────────────────────────────

def erkenne_rsi_divergenz(df: pd.DataFrame, fenster: int = 14, lookback: int = 40):
    close = df['Close']
    if len(close) < fenster + lookback:
        return None

    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=fenster - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=fenster - 1, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, 1e-9)
    rsi_serie = (100 - 100 / (1 + rs)).values

    preis = close.values[-lookback:]
    rsi   = rsi_serie[-lookback:]

    def lokale_tiefs(arr, n=3):
        return [i for i in range(n, len(arr) - n)
                if arr[i] == min(arr[i - n: i + n + 1])]

    def lokale_hochs(arr, n=3):
        return [i for i in range(n, len(arr) - n)
                if arr[i] == max(arr[i - n: i + n + 1])]

    p_tiefs = lokale_tiefs(preis)
    r_tiefs = lokale_tiefs(rsi)
    p_hochs = lokale_hochs(preis)
    r_hochs = lokale_hochs(rsi)

    # Bullische Divergenz: Preis tieferes Tief, RSI höheres Tief
    if len(p_tiefs) >= 2 and len(r_tiefs) >= 2:
        if (preis[p_tiefs[-1]] < preis[p_tiefs[-2]] and
                rsi[r_tiefs[-1]] > rsi[r_tiefs[-2]] and
                abs(p_tiefs[-1] - r_tiefs[-1]) <= 5):
            return 'bullisch'

    # Bärische Divergenz: Preis höheres Hoch, RSI tieferes Hoch
    if len(p_hochs) >= 2 and len(r_hochs) >= 2:
        if (preis[p_hochs[-1]] > preis[p_hochs[-2]] and
                rsi[r_hochs[-1]] < rsi[r_hochs[-2]] and
                abs(p_hochs[-1] - r_hochs[-1]) <= 5):
            return 'bärisch'

    return None

# ── Kerzenformationen Erkennung ───────────────────────────────────────────────

def erkenne_kerzenformation(df: pd.DataFrame) -> list:
    """Erkennt Candlestick-Formationen der letzten Kerzen. Gibt Liste von Dicts zurück."""
    if len(df) < 3:
        return []

    muster = []
    c1 = df.iloc[-3]
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]

    o3, h3, l3, c3v = c3['Open'], c3['High'], c3['Low'], c3['Close']
    body3        = abs(c3v - o3)
    gesamtrange3 = h3 - l3
    if gesamtrange3 < 1e-9:
        return []
    upper_wick3 = h3 - max(c3v, o3)
    lower_wick3 = min(c3v, o3) - l3
    bull3 = c3v >= o3

    o2, h2, l2, c2v = c2['Open'], c2['High'], c2['Low'], c2['Close']
    body2 = abs(c2v - o2)
    bull2 = c2v >= o2

    o1, h1, l1, c1v = c1['Open'], c1['High'], c1['Low'], c1['Close']
    body1 = abs(c1v - o1)
    bull1 = c1v >= o1

    # Doji – Körper extrem klein → allein zurückgeben
    if body3 <= gesamtrange3 * 0.08:
        return [{'name': 'doji', **KERZEN_DEFINITIONEN['doji']}]

    # Spinning Top – kleiner Körper mit langen Schatten auf beiden Seiten
    if (body3 <= gesamtrange3 * 0.3 and
            upper_wick3 > body3 * 0.8 and lower_wick3 > body3 * 0.8):
        muster.append('spinning_top')

    # Hammer / Hanging Man – kleiner Körper oben, langer unterer Schatten
    if (lower_wick3 >= body3 * 2.0 and
            upper_wick3 <= body3 * 0.5 and
            body3 / gesamtrange3 <= 0.35):
        if not bull3 and c2v > c1v:
            muster.append('hanging_man')
        else:
            muster.append('hammer')

    # Inverted Hammer – kleiner Körper unten, langer oberer Schatten (bullisch)
    if (bull3 and
            upper_wick3 >= body3 * 2.0 and
            lower_wick3 <= body3 * 0.5 and
            body3 / gesamtrange3 <= 0.35):
        muster.append('inverted_hammer')

    # Shooting Star – wie Inverted Hammer, aber rote Kerze (bärisch)
    if (not bull3 and
            upper_wick3 >= body3 * 2.0 and
            lower_wick3 <= body3 * 0.5 and
            body3 / gesamtrange3 <= 0.35):
        muster.append('shooting_star')

    # Bullischer Marubozu – große grüne Kerze, kaum Schatten
    if (bull3 and body3 / gesamtrange3 >= 0.85):
        muster.append('bullischer_marubozu')

    # Bärischer Marubozu – große rote Kerze, kaum Schatten
    if (not bull3 and body3 / gesamtrange3 >= 0.85):
        muster.append('baerischer_marubozu')

    # Bullisches Engulfing – grüne Kerze umschließt vorherige rote
    if (bull3 and not bull2 and body2 > 0 and
            o3 <= c2v and c3v >= o2):
        muster.append('bullisches_engulfing')

    # Bärisches Engulfing – rote Kerze umschließt vorherige grüne
    if (not bull3 and bull2 and body2 > 0 and
            o3 >= c2v and c3v <= o2):
        muster.append('baerisches_engulfing')

    # Tweezer Bottom – zwei Kerzen mit fast gleichem Tief (bullisch)
    if (bull3 and not bull2 and
            abs(l2 - l3) / max(l2, 1e-9) < 0.003):
        muster.append('tweezer_bottom')

    # Tweezer Top – zwei Kerzen mit fast gleichem Hoch (bärisch)
    if (not bull3 and bull2 and
            abs(h2 - h3) / max(h2, 1e-9) < 0.003):
        muster.append('tweezer_top')

    # Morgenstern (3 Kerzen): rot → kleiner Mittelteil → große grüne Kerze
    if (not bull1 and
            body2 <= body1 * 0.4 and
            bull3 and body3 >= body1 * 0.5 and
            c3v > (o1 + c1v) / 2):
        muster.append('morgenstern')

    # Abendstern (3 Kerzen): grün → kleiner Mittelteil → große rote Kerze
    if (bull1 and
            body2 <= body1 * 0.4 and
            not bull3 and body3 >= body1 * 0.5 and
            c3v < (o1 + c1v) / 2):
        muster.append('abendstern')

    # Anzahl beteiligter Kerzen je Muster (für Zeitstempel-Spanne)
    _KERZEN_ANZAHL = {
        'bullisches_engulfing': 2, 'baerisches_engulfing': 2,
        'tweezer_bottom': 2,       'tweezer_top': 2,
        'morgenstern': 3,          'abendstern': 3,
    }
    result = []
    for n in muster:
        if n not in KERZEN_DEFINITIONEN:
            continue
        anzahl = _KERZEN_ANZAHL.get(n, 1)
        eintrag = {
            'name':   n,
            **KERZEN_DEFINITIONEN[n],
            'kerzen': anzahl,
            'zeit':   _fmt_zeit(df.index[-1]),
        }
        if anzahl > 1:
            eintrag['zeit_start'] = _fmt_zeit(df.index[-anzahl])
        result.append(eintrag)
    return result


# ── Chart-Muster Erkennung ────────────────────────────────────────────────────

def erkenne_chartmuster(df: pd.DataFrame, fenster: int = 5) -> list:
    """Erkennt übergeordnete Chart-Muster (17 Muster-Typen, Dominanz-Filter)."""
    if len(df) < 30:
        return []

    n     = len(df)
    lb    = n - 1             # gesamten gewählten Zeitraum analysieren
    h_arr = df['High'].values[-lb:]
    l_arr = df['Low'].values[-lb:]
    c_arr = df['Close'].values[-lb:]
    lb_n  = len(h_arr)
    w     = max(3, fenster // 2)

    def lok_hochs(arr, w=3):
        return [i for i in range(w, len(arr) - w)
                if arr[i] == max(arr[i - w: i + w + 1])]

    def lok_tiefs(arr, w=3):
        return [i for i in range(w, len(arr) - w)
                if arr[i] == min(arr[i - w: i + w + 1])]

    h_idx = lok_hochs(h_arr, w)
    l_idx = lok_tiefs(l_arr, w)

    # muster_meta: list of (name, start_arr_idx) — start_arr_idx im lookback-Array
    muster_meta: list[tuple[str, int]] = []

    # ── Double Bottom ─────────────────────────────────────────────────────────
    if len(l_idx) >= 2:
        t1_i, t2_i = l_idx[-2], l_idx[-1]
        t1, t2 = l_arr[t1_i], l_arr[t2_i]
        if (t2_i > t1_i + 5 and
                abs(t1 - t2) / max(t1, 1e-9) < 0.04):
            peak = max(h_arr[t1_i: t2_i + 1])
            if (peak - min(t1, t2)) / max(peak, 1e-9) > 0.03:
                muster_meta.append(('double_bottom', t1_i))

    # ── Triple Bottom (ersetzt Double Bottom wenn erkannt) ───────────────────
    if len(l_idx) >= 3:
        t1_i, t2_i, t3_i = l_idx[-3], l_idx[-2], l_idx[-1]
        t1, t2, t3 = l_arr[t1_i], l_arr[t2_i], l_arr[t3_i]
        t_mean = (t1 + t2 + t3) / 3
        if (t3_i > t1_i + 8 and
                max(abs(t1 - t_mean), abs(t2 - t_mean), abs(t3 - t_mean)) / max(t_mean, 1e-9) < 0.04):
            muster_meta = [(nm, s) for nm, s in muster_meta if nm != 'double_bottom']
            muster_meta.append(('triple_bottom', t1_i))

    # ── Double Top ────────────────────────────────────────────────────────────
    if len(h_idx) >= 2:
        p1_i, p2_i = h_idx[-2], h_idx[-1]
        p1, p2 = h_arr[p1_i], h_arr[p2_i]
        if (p2_i > p1_i + 5 and
                abs(p1 - p2) / max(p1, 1e-9) < 0.04):
            trough = min(l_arr[p1_i: p2_i + 1])
            if (max(p1, p2) - trough) / max(max(p1, p2), 1e-9) > 0.03:
                muster_meta.append(('double_top', p1_i))

    # ── Triple Top (ersetzt Double Top wenn erkannt) ──────────────────────────
    if len(h_idx) >= 3:
        p1_i, p2_i, p3_i = h_idx[-3], h_idx[-2], h_idx[-1]
        p1, p2, p3 = h_arr[p1_i], h_arr[p2_i], h_arr[p3_i]
        p_mean = (p1 + p2 + p3) / 3
        if (p3_i > p1_i + 8 and
                max(abs(p1 - p_mean), abs(p2 - p_mean), abs(p3 - p_mean)) / max(p_mean, 1e-9) < 0.04):
            muster_meta = [(nm, s) for nm, s in muster_meta if nm != 'double_top']
            muster_meta.append(('triple_top', p1_i))

    # ── Kopf-Schulter (bärisch) ───────────────────────────────────────────────
    if len(h_idx) >= 3:
        ls_i, hd_i, rs_i = h_idx[-3], h_idx[-2], h_idx[-1]
        ls, hd, rs = h_arr[ls_i], h_arr[hd_i], h_arr[rs_i]
        if (hd > ls * 1.03 and hd > rs * 1.03 and
                abs(ls - rs) / max(ls, 1e-9) < 0.07 and
                rs_i > hd_i + 4 and hd_i > ls_i + 4):
            nl_l     = min(l_arr[ls_i: hd_i + 1])
            nl_r     = min(l_arr[hd_i: rs_i + 1])
            neckline = (nl_l + nl_r) / 2
            if c_arr[-1] <= neckline * 1.03:
                muster_meta.append(('head_shoulders', ls_i))

    # ── Invertierter Kopf-Schulter (bullisch) ─────────────────────────────────
    if len(l_idx) >= 3:
        ls_i, hd_i, rs_i = l_idx[-3], l_idx[-2], l_idx[-1]
        ls, hd, rs = l_arr[ls_i], l_arr[hd_i], l_arr[rs_i]
        if (hd < ls * 0.97 and hd < rs * 0.97 and
                abs(ls - rs) / max(ls, 1e-9) < 0.07 and
                rs_i > hd_i + 4 and hd_i > ls_i + 4):
            nl_l     = max(h_arr[ls_i: hd_i + 1])
            nl_r     = max(h_arr[hd_i: rs_i + 1])
            neckline = (nl_l + nl_r) / 2
            if c_arr[-1] >= neckline * 0.97:
                muster_meta.append(('inv_head_shoulders', ls_i))

    # H&S gegenseitig ausschließend
    has_hs  = any(nm == 'head_shoulders'     for nm, _ in muster_meta)
    has_ihs = any(nm == 'inv_head_shoulders' for nm, _ in muster_meta)
    if has_hs and has_ihs:
        muster_meta = [(nm, s) for nm, s in muster_meta
                       if nm not in ('head_shoulders', 'inv_head_shoulders')]

    # ── Flag / Pennant ────────────────────────────────────────────────────────
    if lb_n >= 20:
        split  = lb_n // 3
        flag_h = h_arr[split:]
        flag_l = l_arr[split:]
        flag_c = c_arr[split:]

        if len(flag_c) >= 5:
            x        = np.arange(len(flag_c))
            fh_mean  = max(abs(np.mean(flag_h)), 1e-9)
            fl_mean  = max(abs(np.mean(flag_l)), 1e-9)
            fc_mean  = max(abs(np.mean(flag_c)), 1e-9)
            fh_sl    = np.polyfit(x, flag_h, 1)[0] / fh_mean * 100
            fl_sl    = np.polyfit(x, flag_l, 1)[0] / fl_mean * 100
            fc_sl    = np.polyfit(x, flag_c, 1)[0] / fc_mean * 100
            flag_rng = (max(flag_c) - min(flag_c)) / fc_mean * 100
            pennant  = fh_sl < -0.15 and fl_sl > 0.15  # konvergierende Consolidation

            bull_pole = (c_arr[split] - c_arr[0]) / max(abs(c_arr[0]), 1e-9) * 100
            bear_pole = (c_arr[0] - c_arr[split]) / max(abs(c_arr[0]), 1e-9) * 100

            if bull_pole > 5 and flag_rng < bull_pole * 0.6:
                if pennant:
                    muster_meta.append(('bull_pennant', split))
                elif -4 < fc_sl < 0.5:
                    muster_meta.append(('bull_flag', 0))
            elif bear_pole > 5 and flag_rng < bear_pole * 0.6:
                if pennant:
                    muster_meta.append(('bear_pennant', split))
                elif -0.5 < fc_sl < 4:
                    muster_meta.append(('bear_flag', 0))

    # ── Dreiecke, Keile & Erweiterungsdreiecke — gegenseitig ausschließend ────
    tri_name  = None
    tri_start = 0
    if len(h_idx) >= 2 and len(l_idx) >= 2:
        # Mindestens 3 Swing-Punkte pro Seite für zuverlässigere Erkennung
        rec_h_idx = h_idx[-4:] if len(h_idx) >= 4 else h_idx[-3:] if len(h_idx) >= 3 else h_idx[-2:]
        rec_l_idx = l_idx[-4:] if len(l_idx) >= 4 else l_idx[-3:] if len(l_idx) >= 3 else l_idx[-2:]
        rec_h  = [h_arr[i] for i in rec_h_idx]
        rec_l  = [l_arr[i] for i in rec_l_idx]
        h_mean = max(np.mean(rec_h), 1e-9)
        l_mean = max(np.mean(rec_l), 1e-9)
        h_cv   = np.std(rec_h) / h_mean * 100
        l_cv   = np.std(rec_l) / l_mean * 100
        h_sl   = np.polyfit(range(len(rec_h)), rec_h, 1)[0] / h_mean * 100
        l_sl   = np.polyfit(range(len(rec_l)), rec_l, 1)[0] / l_mean * 100
        tri_start = min(rec_h_idx[0], rec_l_idx[0])

        if h_cv < 1.5 and l_sl > 0:
            tri_name = 'ascending_triangle'          # flache Hochs, steigende Tiefs
        elif l_cv < 1.5 and h_sl < 0:
            tri_name = 'descending_triangle'         # fallende Hochs, flache Tiefs
        elif h_sl > 0.1 and l_sl > 0.1 and l_sl > h_sl * 1.2:
            tri_name = 'rising_wedge'                # beide steigen, Tiefs schneller → Keil
        elif h_sl < -0.1 and l_sl < -0.1 and h_sl < l_sl * 1.2:
            tri_name = 'falling_wedge'               # beide fallen, Hochs schneller → Keil
        elif h_sl < -0.1 and l_sl > 0.1:
            tri_name = 'symmetrical_triangle'        # Hochs fallen + Tiefs steigen = konvergierend
        elif h_sl > 0.1 and l_sl < -0.1:
            # Erweiterungsdreieck: Hochs steigen + Tiefs fallen = divergierend
            t_high = max(h_arr[tri_start:])
            t_low  = min(l_arr[tri_start:])
            t_mid  = (t_high + t_low) / 2
            # Preisposition im Dreieck bestimmt Richtung
            tri_name = ('bear_expanding_triangle' if c_arr[-1] > t_mid
                        else 'bull_expanding_triangle')

    if tri_name:
        muster_meta.append((tri_name, tri_start))

    # ── Dominanz-Filter: nur konsistente, nicht-widersprüchliche Ausgabe ──────
    # Maximal ein Muster pro Gruppe; bullische + bärische Reversals schließen sich aus
    _REV_BULL  = {'triple_bottom', 'double_bottom', 'inv_head_shoulders',
                  'falling_wedge', 'bull_expanding_triangle'}
    _REV_BEAR  = {'triple_top', 'double_top', 'head_shoulders',
                  'rising_wedge', 'bear_expanding_triangle'}
    _CONT_BULL = {'bull_flag', 'bull_pennant', 'ascending_triangle'}
    _CONT_BEAR = {'bear_flag', 'bear_pennant', 'descending_triangle'}
    _NEUTRAL   = {'symmetrical_triangle'}

    def _bestes(gruppe):
        kandidaten = [(nm, s) for nm, s in muster_meta if nm in gruppe]
        if not kandidaten:
            return None
        return max(kandidaten, key=lambda x: abs(CHARTMUSTER_DEFINITIONEN[x[0]]['score']))

    rev_bull  = _bestes(_REV_BULL)
    rev_bear  = _bestes(_REV_BEAR)
    cont_bull = _bestes(_CONT_BULL)
    cont_bear = _bestes(_CONT_BEAR)
    neutral   = next(((nm, s) for nm, s in muster_meta if nm in _NEUTRAL), None)

    # Gegensätzliche Reversals: nur das stärkere behalten
    if rev_bull and rev_bear:
        sb = CHARTMUSTER_DEFINITIONEN[rev_bull[0]]['score']
        se = abs(CHARTMUSTER_DEFINITIONEN[rev_bear[0]]['score'])
        if sb >= se:
            rev_bear = None
        else:
            rev_bull = None

    # Continuation darf dem Reversal nicht widersprechen
    if rev_bull:
        cont_bear = None
    if rev_bear:
        cont_bull = None

    muster_meta = [x for x in [rev_bull, rev_bear, cont_bull, cont_bear, neutral]
                   if x is not None]

    # ── Zeitstempel berechnen und Ergebnis aufbauen ───────────────────────────
    result = []
    for name, start_arr_idx in muster_meta:
        if name not in CHARTMUSTER_DEFINITIONEN:
            continue
        df_start_idx = start_arr_idx - lb_n  # negativer Index in df
        eintrag = {
            'name':       name,
            **CHARTMUSTER_DEFINITIONEN[name],
            'zeit_start': _fmt_zeit(df.index[df_start_idx]),
            'zeit':       _fmt_zeit(df.index[-1]),
        }
        result.append(eintrag)
    return result

# ── Daytrading Signal ────────────────────────────────────────────────────────

def berechne_daytrade_signal(levels: dict, ind: dict, aktuell: float,
                              richtung: str, hoch: float, tief: float,
                              bullisch_pct: float = 50.0, intraday: bool = False,
                              kerzen_muster: list = None, chart_muster: list = None,
                              tagesvol_pct: float = None):
    rsi      = ind['rsi']
    ema20    = ind['ema20']
    ema50    = ind['ema50']
    macd     = ind['macd']
    msig     = ind['macd_signal']
    mhist    = ind['macd_hist']
    mhist_p  = ind.get('macd_hist_prev', mhist)
    atr      = ind['atr']
    adx      = ind.get('adx', 0)
    plus_di  = ind.get('plus_di', 0)
    minus_di = ind.get('minus_di', 0)
    vwap     = ind.get('vwap', 0)
    bb_pos   = ind.get('bb_pos', 0.5)
    ema200   = ind['ema200']

    alle_preise = sorted(levels.values())
    supports    = sorted([p for p in alle_preise if p < aktuell * 0.9995], reverse=True)
    resistances = sorted([p for p in alle_preise if p > aktuell * 1.0005])

    # Fallback auf ATR-Projektion wenn Kurs außerhalb aller Fib-Level
    naechster_support   = supports[0]    if supports    else aktuell - atr * 2
    naechste_resistance = resistances[0] if resistances else aktuell + atr * 2

    abstand_sup_pct = (aktuell - naechster_support)   / aktuell * 100
    abstand_res_pct = (naechste_resistance - aktuell) / aktuell * 100

    long_score  = 0
    short_score = 0
    gruende_long  = []
    gruende_short = []

    # Gewichtungen: Intraday fokussiert auf VWAP/RSI/MACD, Swing auf Fibonacci
    w_rsi   = 4 if intraday else 3
    w_macd  = 4 if intraday else 3
    w_vwap  = 5 if intraday else 3
    w_stoch = 3 if intraday else 2
    w_fib   = 0 if intraday else 2  # Fib-Level auf Intraday nicht aussagekräftig

    # RSI
    if rsi < 30:
        long_score += w_rsi;      gruende_long.append(f'RSI stark überverkauft ({rsi:.0f})')
    elif rsi < 45:
        long_score += w_rsi // 2; gruende_long.append(f'RSI überverkauft ({rsi:.0f})')
    elif rsi > 70:
        short_score += w_rsi;     gruende_short.append(f'RSI stark überkauft ({rsi:.0f})')
    elif rsi > 55:
        short_score += w_rsi // 2; gruende_short.append(f'RSI leicht überkauft ({rsi:.0f})')

    # MACD (echtes Kreuz)
    if mhist > 0 and mhist_p <= 0:
        long_score += w_macd;         gruende_long.append('Frisches MACD-Kaufkreuz')
    elif macd > msig:
        long_score += w_macd - 1;     gruende_long.append('MACD bullisches Momentum')
    elif mhist < 0 and mhist_p >= 0:
        short_score += w_macd;        gruende_short.append('Frisches MACD-Verkaufskreuz')
    elif macd < msig:
        short_score += w_macd - 1;    gruende_short.append('MACD bärisches Momentum')

    # EMA-Trend (kurzfristig)
    if aktuell > ema20 > ema50:
        long_score += 2;  gruende_long.append('Aufwärtstrend (Preis > EMA20 > EMA50)')
    elif aktuell < ema20 < ema50:
        short_score += 2; gruende_short.append('Abwärtstrend (Preis < EMA20 < EMA50)')

    # EMA200 – übergeordneter Trend (täglich für Intraday, Intervall-basiert für Swing)
    if aktuell > ema200:
        long_score  += 2; gruende_long.append(f'Über EMA200 ({ema200:.2f}) – übergeordnet bullisch')
    else:
        short_score += 2; gruende_short.append(f'Unter EMA200 ({ema200:.2f}) – übergeordnet bärisch')

    # Fibonacci-Position (nur für Swing-Charts, nicht Intraday)
    if w_fib > 0:
        if abstand_sup_pct < abstand_res_pct and abstand_sup_pct < 1.5:
            long_score += w_fib;  gruende_long.append(f'Nah am Fib-Support ({naechster_support:.2f})')
        elif abstand_res_pct < abstand_sup_pct and abstand_res_pct < 1.5:
            short_score += w_fib; gruende_short.append(f'Nah am Fib-Widerstand ({naechste_resistance:.2f})')

    # VWAP – dominanter Intraday-Indikator
    if vwap > 0:
        if aktuell > vwap * 1.002:
            long_score += w_vwap;  gruende_long.append(f'Über VWAP ({vwap:.2f}) – bullische Bias')
        elif aktuell < vwap * 0.998:
            short_score += w_vwap; gruende_short.append(f'Unter VWAP ({vwap:.2f}) – bärische Bias')

    # ADX – Trend-Stärke
    if adx > 20:
        if plus_di > minus_di:
            long_score += 2;  gruende_long.append(f'ADX {adx:.0f}: Aufwärtstrend bestätigt')
        else:
            short_score += 2; gruende_short.append(f'ADX {adx:.0f}: Abwärtstrend bestätigt')

    # Bollinger Bands
    if bb_pos <= 0.1:
        long_score += 2;  gruende_long.append('Am unteren Bollinger Band – Reversal-Zone')
    elif bb_pos >= 0.9:
        short_score += 2; gruende_short.append('Am oberen Bollinger Band – Reversal-Zone')

    # Stochastic
    sk   = ind.get('stoch_k', 50)
    sk_p = ind.get('stoch_k_prev', sk)
    if sk < 20 and sk > sk_p:
        long_score += w_stoch;      gruende_long.append(f'Stochastic dreht aufwärts aus überverkaufter Zone ({sk:.0f})')
    elif sk < 20:
        long_score += w_stoch - 1;  gruende_long.append(f'Stochastic überverkauft ({sk:.0f})')
    elif sk > 80 and sk < sk_p:
        short_score += w_stoch;     gruende_short.append(f'Stochastic dreht abwärts aus überkaufter Zone ({sk:.0f})')
    elif sk > 80:
        short_score += w_stoch - 1; gruende_short.append(f'Stochastic überkauft ({sk:.0f})')

    # Swing-Richtung
    if richtung == 'aufwärts': long_score  += 1
    else:                      short_score += 1

    # Candlestick- & Chart-Muster
    for km in (kerzen_muster or []):
        pts = max(-3, min(3, km['score'] // 4))
        if pts > 0:
            long_score  += pts; gruende_long.append(km['text'])
        elif pts < 0:
            short_score += abs(pts); gruende_short.append(km['text'])
    for cm in (chart_muster or []):
        pts = max(-4, min(4, cm['score'] // 5))
        if pts > 0:
            long_score  += pts; gruende_long.append(cm['text'])
        elif pts < 0:
            short_score += abs(pts); gruende_short.append(cm['text'])

    # Volumen-Bestätigung (amplifiziert die führende Seite)
    vr = ind.get('volumen_ratio', 1.0)
    if vr >= 2.0:
        if long_score >= short_score:
            long_score  += 3; gruende_long.append(f'Sehr hohes Volumen ({vr:.1f}x) – Aufwärtsmomentum bestätigt')
        else:
            short_score += 3; gruende_short.append(f'Sehr hohes Volumen ({vr:.1f}x) – Abwärtsmomentum bestätigt')
    elif vr >= 1.4:
        if long_score >= short_score:
            long_score  += 2; gruende_long.append(f'Überdurchschnittliches Volumen ({vr:.1f}x)')
        else:
            short_score += 2; gruende_short.append(f'Überdurchschnittliches Volumen ({vr:.1f}x)')

    # Gesamtbild
    if bullisch_pct >= 65:
        long_score += 3;  gruende_long.append(f'Gesamtanalyse bullisch ({bullisch_pct:.0f}%)')
    elif bullisch_pct >= 55:
        long_score += 1
    elif bullisch_pct <= 35:
        short_score += 3; gruende_short.append(f'Gesamtanalyse bärisch ({100-bullisch_pct:.0f}%)')
    elif bullisch_pct <= 45:
        short_score += 1

    dt_richtung = 'LONG' if long_score >= short_score else 'SHORT'
    total    = long_score + short_score or 1
    staerke  = round(max(long_score, short_score) / total * 100)
    gruende  = gruende_long if dt_richtung == 'LONG' else gruende_short
    widerspruch = (dt_richtung == 'LONG'  and bullisch_pct < 40) or \
                  (dt_richtung == 'SHORT' and bullisch_pct > 60)

    # ── Preisziele (volatilitätsbasiert mit Fibonacci-Confluence) ──────────────
    # Ziel-Chance/Risiko-Verhältnis: der Take-Profit muss mindestens das
    # ZIEL_RR-fache des Stop-Abstands entfernt sein, sonst lohnt der Trade nicht.
    ZIEL_RR = 2.0

    # Risiko-Einheit: Bei Intraday die durchschnittliche Tagesspanne (ADR) als
    # Maßstab – die ATR der kleinen Kerzen wäre für Tagesziele zu eng. Sonst
    # (Swing-Charts) die ATR der Tages-/Wochenkerzen.
    if intraday and tagesvol_pct:
        adr_abs   = aktuell * tagesvol_pct / 100.0
        risk_unit = adr_abs * 0.25          # Stop ~1/4 der Tagesspanne
        tp_cap    = adr_abs * 0.9           # Ziel realistisch im Tagesrange halten
    else:
        adr_abs   = None
        risk_unit = (atr if atr and atr > 0 else aktuell * 0.005) * 1.2
        tp_cap    = None

    if dt_richtung == 'LONG':
        # Stop-Loss unter Support, Distanz auf [0.5 … 1.5]×risk_unit begrenzt
        fib_sl_dist = max(0.0, aktuell - naechster_support)
        sl_dist     = max(risk_unit * 0.5, min(fib_sl_dist + risk_unit * 0.3, risk_unit * 1.5))
        stop_loss   = aktuell - sl_dist

        # Take-Profit: nächster Widerstand, mind. ZIEL_RR × Risiko, im Tagesrange
        tp_dist = max(naechste_resistance - aktuell, sl_dist * ZIEL_RR)
        if tp_cap:
            tp_dist = min(tp_dist, tp_cap)
        take_profit = aktuell + tp_dist
    else:
        fib_sl_dist = max(0.0, naechste_resistance - aktuell)
        sl_dist     = max(risk_unit * 0.5, min(fib_sl_dist + risk_unit * 0.3, risk_unit * 1.5))
        stop_loss   = aktuell + sl_dist

        tp_dist = max(aktuell - naechster_support, sl_dist * ZIEL_RR)
        if tp_cap:
            tp_dist = min(tp_dist, tp_cap)
        take_profit = aktuell - tp_dist

    sl_pct = sl_dist / aktuell * 100 if aktuell > 0 else 0.5
    tp_pct = max(0.01, tp_dist / aktuell * 100 if aktuell > 0 else 0.01)
    rr = round(tp_pct / sl_pct, 1) if sl_pct > 0 else 0

    # ── Gates ────────────────────────────────────────────────────────────────
    kein_signal = abs(long_score - short_score) <= 1

    # R:R-Gate für alle Zeitebenen: unter 1.5:1 ist das Verhältnis zu schlecht
    # (z.B. wenn die Tagesvolatilität kein vernünftiges Ziel mehr zulässt).
    if rr < 1.5:
        kein_signal = True

    # ADX-Gate: kein Signal bei extremem Range-Markt
    adx_min = 10 if intraday else 12
    if adx < adx_min:
        kein_signal = True

    # VWAP-Gate: LONG nur über VWAP, SHORT nur unter VWAP
    if vwap > 0:
        if dt_richtung == 'LONG'  and aktuell < vwap * 0.995: kein_signal = True
        if dt_richtung == 'SHORT' and aktuell > vwap * 1.005: kein_signal = True

    return {
        'richtung':    dt_richtung,
        'kein_signal': kein_signal,
        'staerke':     staerke,
        'einstieg':    round(aktuell,      2),
        'take_profit': round(take_profit,  2),
        'stop_loss':   round(stop_loss,    2),
        'tp_pct':      round(tp_pct,       2),
        'sl_pct':      round(sl_pct,       2),
        'rr':          rr,
        'gruende':     gruende,
        'long_score':  long_score,
        'widerspruch': widerspruch,
        'short_score': short_score,
        'tagesvol_pct': round(tagesvol_pct, 2) if tagesvol_pct else None,
    }

# ── Handelssignal Algorithmus ─────────────────────────────────────────────────

SIGNAL_TEXTE = {
    'KAUFEN':      '🟢 KAUFSIGNAL',
    'BEOBACHTEN':  '🟡 BEOBACHTEN',
    'WARTEN':      '⚪ ABWARTEN',
    'VORSICHT':    '🟠 VORSICHT',
    'MEIDEN':      '🔴 MEIDEN',
    'VERKAUFEN':   '🔻 VERKAUFSSIGNAL',
}

SIGNAL_FARBEN = {
    'KAUFEN':     'success',
    'BEOBACHTEN': 'warning',
    'WARTEN':     'secondary',
    'VORSICHT':   'orange',
    'MEIDEN':     'danger',
    'VERKAUFEN':  'danger',
}

KEY_FIB_LEVELS = {'61,8 %', '50,0 %', '38,2 %', '23,6 %'}

def berechne_handelssignal(df, levels, ind, aktuell, richtung, hoch, tief,
                           kerzen_muster=None, chart_muster=None):
    score         = 0
    begruendungen = []
    warnungen     = []
    bedingungen   = []

    alle_preise = sorted(levels.values())
    supports    = sorted([p for p in alle_preise if p <= aktuell * 1.005], reverse=True)
    resistances = sorted([p for p in alle_preise if p >= aktuell * 0.995])

    naechster_support   = supports[0]    if supports    else tief
    naechste_resistance = resistances[0] if resistances else hoch

    atr      = ind['atr']
    rsi      = ind['rsi']
    ema20    = ind['ema20']
    ema50    = ind['ema50']
    ema200   = ind['ema200']
    macd     = ind['macd']
    msig     = ind['macd_signal']
    mhist    = ind['macd_hist']
    mhist_p  = ind.get('macd_hist_prev', mhist)
    vr       = ind['volumen_ratio']
    adx      = ind.get('adx', 0)
    plus_di  = ind.get('plus_di', 0)
    minus_di = ind.get('minus_di', 0)
    vwap     = ind.get('vwap', 0)
    bb_pos   = ind.get('bb_pos', 0.5)
    bb_breite = ind.get('bb_breite', 5.0)

    # ── 1. Fibonacci-Support-Nähe ─────────────────────────────────────────────
    abstand_support_pct = (aktuell - naechster_support)   / aktuell * 100
    abstand_resist_pct  = (naechste_resistance - aktuell) / aktuell * 100

    level_name = next((n for n, p in levels.items()
                       if abs(p - naechster_support) / max(naechster_support, 1) < 0.003), '')

    if abstand_support_pct <= 1.0:
        score += 30
        begruendungen.append(f'Preis direkt auf Fibonacci-Support {level_name} ({naechster_support:.2f})')
    elif abstand_support_pct <= 2.5:
        score += 18
        begruendungen.append(f'Preis nahe Fibonacci-Support {level_name} ({naechster_support:.2f}, {abstand_support_pct:.1f}% entfernt)')
    elif abstand_support_pct <= 5.0:
        score += 8
        bedingungen.append(f'Auf Rücksetzer zum Support {naechster_support:.2f} warten')

    if level_name in KEY_FIB_LEVELS and abstand_support_pct <= 3.0:
        score += 12
        begruendungen.append(f'Goldene Fibonacci-Zone ({level_name}) – besonders starker Support')

    if abstand_resist_pct <= 1.5:
        score -= 22
        warnungen.append(f'Preis nahe Fibonacci-Widerstand {naechste_resistance:.2f} – Rücksetzer möglich')
    elif abstand_resist_pct <= 3.0:
        score -= 10
        warnungen.append(f'Widerstand bei {naechste_resistance:.2f} in Reichweite')

    # ── 2. Trend (EMA) ────────────────────────────────────────────────────────
    if aktuell > ema200:
        score += 15
        begruendungen.append(f'Über EMA200 ({ema200:.2f}) – langfristiger Aufwärtstrend')
    else:
        score -= 12
        warnungen.append(f'Unter EMA200 ({ema200:.2f}) – langfristiger Abwärtstrend')

    if aktuell > ema50:
        score += 8
        begruendungen.append(f'Über EMA50 ({ema50:.2f}) – mittelfristiger Aufwärtstrend')
    else:
        score -= 6
        warnungen.append(f'Unter EMA50 ({ema50:.2f}) – mittelfristiger Abwärtstrend')

    if ema20 > ema50 > ema200:
        score += 8
        begruendungen.append('EMA-Fächer bullisch (EMA20 > EMA50 > EMA200)')
    elif ema20 < ema50 < ema200:
        score -= 8
        warnungen.append('EMA-Fächer bärisch (EMA20 < EMA50 < EMA200)')

    # ── 3. RSI ────────────────────────────────────────────────────────────────
    if rsi < 25:
        score += 22
        begruendungen.append(f'RSI extrem überverkauft ({rsi:.0f}) – starkes Bounce-Signal')
    elif rsi < 35:
        score += 14
        begruendungen.append(f'RSI überverkauft ({rsi:.0f})')
    elif rsi < 45:
        score += 6
    elif rsi > 75:
        score -= 22
        warnungen.append(f'RSI extrem überkauft ({rsi:.0f}) – Rücksetzer sehr wahrscheinlich')
    elif rsi > 65:
        score -= 12
        warnungen.append(f'RSI überkauft ({rsi:.0f})')

    # ── 4. MACD (echtes Kreuz) ────────────────────────────────────────────────
    if mhist > 0 and mhist_p <= 0:
        score += 15
        begruendungen.append('Frisches MACD-Kaufkreuz – Momentum dreht bullisch')
    elif macd > msig and mhist > 0:
        score += 10
        begruendungen.append('MACD über Signallinie – bullisches Momentum')
    elif mhist < 0 and mhist_p >= 0:
        score -= 15
        warnungen.append('Frisches MACD-Verkaufskreuz – Momentum dreht bärisch')
    elif macd < msig and mhist < 0:
        score -= 10
        warnungen.append('MACD unter Signallinie – bärisches Momentum')

    # ── 5. Volumen ────────────────────────────────────────────────────────────
    if vr >= 2.0:
        score += 12
        begruendungen.append(f'Sehr hohes Volumen ({vr:.1f}x) – starke Bestätigung')
    elif vr >= 1.4:
        score += 6
        begruendungen.append(f'Überdurchschnittliches Volumen ({vr:.1f}x)')

    # ── 6. RSI-Divergenz ──────────────────────────────────────────────────────
    divergenz = erkenne_rsi_divergenz(df)
    if divergenz == 'bullisch':
        score += 18
        begruendungen.append('Bullische RSI-Divergenz – Trendwende-Signal')
    elif divergenz == 'bärisch':
        score -= 16
        warnungen.append('Bärische RSI-Divergenz – Schwäche-Signal')

    # ── 7. Kerzenformationen & Chart-Muster ───────────────────────────────────
    for km in (kerzen_muster or []):
        score += km['score']
        if km['score'] > 0:   begruendungen.append(km['text'])
        elif km['score'] < 0: warnungen.append(km['text'])
        else:                 bedingungen.append(km['text'])
    for cm in (chart_muster or []):
        score += cm['score']
        if cm['score'] > 0:   begruendungen.append(cm['text'])
        elif cm['score'] < 0: warnungen.append(cm['text'])
        else:                 bedingungen.append(cm['text'])

    # ── 8. Swing-Richtung ─────────────────────────────────────────────────────
    if richtung == 'aufwärts':
        score += 5
    else:
        score -= 5
        warnungen.append('Primärer Swing zeigt abwärts – erhöhtes Rückschlagrisiko')

    # ── 9. VWAP ──────────────────────────────────────────────────────────────
    if vwap > 0:
        if aktuell > vwap * 1.003:
            score += 10
            begruendungen.append(f'Über VWAP ({vwap:.2f}) – institutionell bullisch')
        elif aktuell < vwap * 0.997:
            score -= 10
            warnungen.append(f'Unter VWAP ({vwap:.2f}) – institutionell bärisch')

    # ── 10. ADX ──────────────────────────────────────────────────────────────
    if adx > 25:
        if plus_di > minus_di:
            score += 10
            begruendungen.append(f'ADX {adx:.0f} + DI+ > DI− – starker Aufwärtstrend')
        else:
            score -= 10
            warnungen.append(f'ADX {adx:.0f} + DI− > DI+ – starker Abwärtstrend')
    elif adx < 15:
        score -= 8
        warnungen.append(f'ADX {adx:.0f} – Range-Markt, Trend-Signale unzuverlässig')

    # ── 11. Bollinger Bands ───────────────────────────────────────────────────
    if bb_pos <= 0.05:
        score += 15
        begruendungen.append('Preis am unteren Bollinger Band – starke Überverkauft-Zone')
    elif bb_pos <= 0.15:
        score += 8
        begruendungen.append('Preis nahe unterem Bollinger Band')
    elif bb_pos >= 0.95:
        score -= 15
        warnungen.append('Preis am oberen Bollinger Band – starke Überkauft-Zone')
    elif bb_pos >= 0.85:
        score -= 8
        warnungen.append('Preis nahe oberem Bollinger Band')
    if bb_breite < 2.0:
        bedingungen.append(f'BB-Squeeze aktiv ({bb_breite:.1f}%) – starke Bewegung erwartet, Richtung offen')

    # ── 12. 52-Wochen-Hoch/Tief ──────────────────────────────────────────────
    h52 = ind.get('hoch52w', 0)
    t52 = ind.get('tief52w', 0)
    if h52 > 0 and aktuell > 0:
        abst_h52 = (h52 - aktuell) / aktuell * 100
        if aktuell >= h52 * 0.999:
            score += 10
            begruendungen.append(f'Ausbruch über 52-Wochen-Hoch ({h52:.2f}) – starkes Momentum-Signal')
        elif abst_h52 < 2.0:
            score -= 15
            warnungen.append(f'Preis nahe 52-Wochen-Hoch ({h52:.2f}) – kritische Widerstandszone')
        elif abst_h52 < 5.0:
            score -= 8
            warnungen.append(f'52-Wochen-Hoch bei {h52:.2f} in Sichtweite')
    if t52 > 0 and aktuell > 0:
        abst_t52 = (aktuell - t52) / aktuell * 100
        if abst_t52 < 3.0:
            score += 12
            begruendungen.append(f'Preis nahe 52-Wochen-Tief ({t52:.2f}) – starker historischer Boden')

    # ── 13. Stochastic ───────────────────────────────────────────────────────
    sk   = ind.get('stoch_k', 50)
    sk_p = ind.get('stoch_k_prev', sk)
    if sk < 20:
        if sk > sk_p:
            score += 12
            begruendungen.append(f'Stochastic dreht aufwärts aus überverkaufter Zone ({sk:.0f}) – Kaufsignal')
        else:
            score += 6
    elif sk > 80:
        if sk < sk_p:
            score -= 12
            warnungen.append(f'Stochastic dreht abwärts aus überkaufter Zone ({sk:.0f}) – Verkaufssignal')
        else:
            score -= 6
            warnungen.append(f'Stochastic überkauft ({sk:.0f})')

    # ── Signal-Typ ────────────────────────────────────────────────────────────
    if   score >= 60:  typ = 'KAUFEN'
    elif score >= 35:  typ = 'BEOBACHTEN'
    elif score >= 10:  typ = 'WARTEN'
    elif score >= -10: typ = 'VORSICHT'
    elif score >= -45: typ = 'MEIDEN'
    else:              typ = 'VERKAUFEN'

    ist_short = (typ == 'VERKAUFEN')
    if ist_short:
        staerke = max(5, min(95, int(-score * 0.9 + 50)))
    else:
        staerke = max(5, min(95, int(score * 0.9 + 50)))

    if not ist_short:
        # ── LONG: Einstieg ────────────────────────────────────────────────────
        if abstand_support_pct <= 2.5 and score >= 35:
            einstieg = aktuell
            bedingungen.insert(0, 'Einstieg jetzt zum aktuellen Kurs möglich')
        elif score >= 35:
            einstieg = naechster_support * 1.005
            bedingungen.insert(0, f'Auf Rücksetzer zum Support {naechster_support:.2f} warten, dann einsteigen')
        else:
            einstieg = aktuell
            bedingungen.insert(0, 'Kein klares Kaufsignal – besser abwarten')

        # ── LONG: Stop-Loss ───────────────────────────────────────────────────
        stop_loss     = naechster_support - (atr * 1.2)
        stop_loss_pct = (einstieg - stop_loss) / einstieg * 100 if einstieg > 0 else 5.0
        if stop_loss_pct < 0.5:
            stop_loss     = einstieg * 0.995
            stop_loss_pct = 0.5
        elif stop_loss_pct > 15:
            if typ == 'KAUFEN':
                typ = 'BEOBACHTEN'
            warnungen.append(f'Stop-Loss zu weit ({stop_loss_pct:.1f}%) – Position zu riskant')
            stop_loss     = einstieg * 0.88
            stop_loss_pct = 12.0

        # ── LONG: Kursziele ───────────────────────────────────────────────────
        ziele_preise = sorted([p for p in alle_preise if p > einstieg * 1.005])
        while len(ziele_preise) < 3:
            letztes = ziele_preise[-1] if ziele_preise else einstieg
            ziele_preise.append(round(letztes + atr * 3, 2))
        ziel_1, ziel_2, ziel_3 = ziele_preise[0], ziele_preise[1], ziele_preise[2]
        z1_pct = round((ziel_1 - einstieg) / einstieg * 100, 1)
        z2_pct = round((ziel_2 - einstieg) / einstieg * 100, 1)
        z3_pct = round((ziel_3 - einstieg) / einstieg * 100, 1)
        rr1    = round(z1_pct / stop_loss_pct, 1) if stop_loss_pct > 0 else 0
        rr2    = round(z2_pct / stop_loss_pct, 1) if stop_loss_pct > 0 else 0
        rr3    = round(z3_pct / stop_loss_pct, 1) if stop_loss_pct > 0 else 0

        # ── Gate: R:R-Minimum 2:1 ─────────────────────────────────────────────
        if rr1 < 2.0 and typ == 'KAUFEN':
            typ = 'BEOBACHTEN'
            warnungen.append(f'R:R zu gering ({rr1}:1) – mindestens 2:1 für Kaufsignal erforderlich')

        # ── Gate: Hard-Gates für KAUFEN ───────────────────────────────────────
        if typ == 'KAUFEN':
            gates = 0
            if vwap == 0 or aktuell >= vwap * 0.997:    gates += 1
            if adx >= 15 or abstand_support_pct <= 1.5:  gates += 1
            if rsi < 72:                                  gates += 1
            if aktuell > ema200:                          gates += 1
            if gates < 3:
                typ = 'BEOBACHTEN'
                warnungen.append('Zu viele widersprüchliche Faktoren – kein klares Kaufsignal')

        # ── LONG: Empfehlungen ────────────────────────────────────────────────
        if typ == 'KAUFEN':
            bedingungen.append(f'Stop-Loss bei {stop_loss:.2f} setzen (−{stop_loss_pct:.1f}%)')
            bedingungen.append(f'Bei Ziel 1 ({ziel_1:.2f}) 40% sichern, Rest laufen lassen')
            if rr2 >= 2:
                bedingungen.append(f'R:R bei Ziel 2: {rr2}:1 – sehr attraktiv')
        elif typ == 'BEOBACHTEN':
            bedingungen.append('Auf Bestätigung warten (grüne Kerze, RSI-Anstieg, Volumen)')
            bedingungen.append('Keinen Kauf ohne Bestätigung – zu früh einsteigen kostet Performance')
        elif typ in ('VORSICHT', 'MEIDEN'):
            bedingungen.append('Kein Kauf empfehlenswert – auf bessere Gelegenheit warten')
            bedingungen.append('Bestehende Positionen mit Stop-Loss absichern')

    else:
        # ── SHORT: Einstieg ───────────────────────────────────────────────────
        einstieg = aktuell
        bedingungen.insert(0, 'Leerverkauf / Put-Option zum aktuellen Kurs möglich')

        # ── SHORT: Stop-Loss (über Widerstand) ────────────────────────────────
        stop_loss     = naechste_resistance + (atr * 1.2)
        stop_loss_pct = (stop_loss - einstieg) / einstieg * 100 if einstieg > 0 else 5.0
        if stop_loss_pct < 0.5:
            stop_loss     = einstieg * 1.005
            stop_loss_pct = 0.5
        elif stop_loss_pct > 15:
            typ = 'MEIDEN'
            warnungen.append(f'Stop-Loss zu weit ({stop_loss_pct:.1f}%) – Short-Position zu riskant')
            stop_loss     = einstieg * 1.12
            stop_loss_pct = 12.0

        # ── SHORT: Kursziele (Preise unterhalb) ───────────────────────────────
        ziele_preise = sorted([p for p in alle_preise if p < einstieg * 0.995], reverse=True)
        while len(ziele_preise) < 3:
            letztes = ziele_preise[-1] if ziele_preise else einstieg
            ziele_preise.append(round(letztes - atr * 3, 2))
        ziel_1, ziel_2, ziel_3 = ziele_preise[0], ziele_preise[1], ziele_preise[2]
        z1_pct = round((einstieg - ziel_1) / einstieg * 100, 1)
        z2_pct = round((einstieg - ziel_2) / einstieg * 100, 1)
        z3_pct = round((einstieg - ziel_3) / einstieg * 100, 1)
        rr1    = round(z1_pct / stop_loss_pct, 1) if stop_loss_pct > 0 else 0
        rr2    = round(z2_pct / stop_loss_pct, 1) if stop_loss_pct > 0 else 0
        rr3    = round(z3_pct / stop_loss_pct, 1) if stop_loss_pct > 0 else 0

        # Gate: R:R-Minimum 2:1 für SHORT
        if rr1 < 2.0 and typ == 'VERKAUFEN':
            typ = 'MEIDEN'
            warnungen.append(f'R:R zu gering ({rr1}:1) – mindestens 2:1 für Verkaufssignal erforderlich')

        # SHORT: Bearish-Gründe als Hauptbegründung
        if not begruendungen:
            begruendungen = warnungen[:3]

        if typ == 'VERKAUFEN':
            bedingungen.append(f'Stop-Loss bei {stop_loss:.2f} setzen (+{stop_loss_pct:.1f}%)')
            bedingungen.append(f'Bei Ziel 1 ({ziel_1:.2f}) 40% eindecken, Rest laufen lassen')
            if rr2 >= 2:
                bedingungen.append(f'R:R bei Ziel 2: {rr2}:1 – sehr attraktiv')
        else:
            bedingungen.append('Kein Kauf empfehlenswert – bärisches Umfeld')
            bedingungen.append('Bestehende Positionen mit Stop-Loss absichern')

    return {
        'typ':           typ,
        'text':          SIGNAL_TEXTE[typ],
        'farbe':         SIGNAL_FARBEN[typ],
        'staerke':       staerke,
        'score':         score,
        'ist_short':     ist_short,
        'einstieg':      round(einstieg,  2),
        'stop_loss':     round(stop_loss, 2),
        'stop_loss_pct': round(stop_loss_pct, 1),
        'ziel_1':        round(ziel_1, 2),  'ziel_1_pct': z1_pct,  'rr_1': rr1,
        'ziel_2':        round(ziel_2, 2),  'ziel_2_pct': z2_pct,  'rr_2': rr2,
        'ziel_3':        round(ziel_3, 2),  'ziel_3_pct': z3_pct,  'rr_3': rr3,
        'begruendungen': begruendungen,
        'warnungen':     warnungen,
        'bedingungen':   bedingungen,
        'divergenz':     divergenz,
        'kerzen_muster': kerzen_muster or [],
        'chart_muster':  chart_muster  or [],
        'support':       round(naechster_support,   2) if naechster_support   is not None else round(tief, 2),
        'resistance':    round(naechste_resistance, 2) if naechste_resistance is not None else round(hoch, 2),
    }

# ── Haupt-Analyse-Funktion ────────────────────────────────────────────────────

def analysiere(ticker: str, periode: str = '1y', mit_chart: bool = True):
    cfg      = PERIODEN.get(periode, PERIODEN['1y'])
    intraday = cfg.get('intraday', False)
    df, name, waehrung, fehler = lade_daten(ticker, periode)
    if fehler:
        return {'fehler': fehler}

    # Mindestens 15 Kerzen nötig für sinnvolle Analyse
    if len(df) < 15:
        return {'fehler': f'Zu wenige Datenpunkte für "{PERIODEN.get(periode,{}).get("label", periode)}" — Markt möglicherweise geschlossen oder keine Intraday-Daten verfügbar.'}

    waehrung_symbol = WAEHRUNG_SYMBOLE.get(waehrung, waehrung)

    # Für Intraday: echten tagesbasierten EMA200 laden (Intraday-EMA200 wäre nur Stunden)
    # sowie die durchschnittliche Tagesvolatilität (ADR) für realistische Tagesziele.
    ema200_daily = None
    tagesvol_pct = None
    if intraday:
        try:
            _tk   = yf.Ticker(ticker)
            _df_d = _tk.history(period='1y', interval='1d', auto_adjust=False)
            if not _df_d.empty:
                if isinstance(_df_d.columns, pd.MultiIndex):
                    _df_d.columns = _df_d.columns.get_level_values(0)
                _close_d = _df_d['Close']
                try:
                    _whr = _tk.fast_info.currency or 'USD'
                    _fx  = hole_eur_kurs(_whr)
                    if _fx != 1.0:
                        _close_d = _close_d * _fx
                except Exception:
                    pass
                if len(_close_d) >= 10:
                    ema200_daily = round(_close_d.ewm(span=200, adjust=False).mean().iloc[-1], 4)
                # ADR%: mittlere Tagesspanne (High-Low) relativ zum Close, letzte 14 Tage.
                # Als Verhältnis währungsunabhängig → keine FX-Umrechnung nötig.
                _range_pct = ((_df_d['High'] - _df_d['Low']) / _df_d['Close'].replace(0, np.nan) * 100).dropna().tail(14)
                if len(_range_pct) >= 5:
                    tagesvol_pct = round(float(_range_pct.mean()), 2)
        except Exception:
            pass

    try:
        # Technische Indikatoren
        ind     = berechne_indikatoren(df, intraday=intraday, ema200_override=ema200_daily)
        aktuell = ind['aktuell']

        # Swing-Erkennung
        fenster = cfg.get('fenster', 10)
        if len(df) < fenster * 3:
            fenster = max(2, len(df) // 5)
        hoch, tief, richtung = markantester_swing(df, fenster)

        # Fibonacci-Levels
        levels = berechne_fib_levels(hoch, tief, richtung)

        # Zonen
        zonen = berechne_zonen(levels)

        # Wahrscheinlichkeit
        wkeit, faktoren, support, resistance = berechne_wahrscheinlichkeit(
            aktuell, levels, ind, richtung
        )

        # Muster-Erkennung
        kerzen_muster = erkenne_kerzenformation(df)
        chart_muster  = erkenne_chartmuster(df, fenster)

        # Handelssignal
        signal = berechne_handelssignal(df, levels, ind, aktuell, richtung, hoch, tief,
                                         kerzen_muster, chart_muster)

        # Daytrading Signal
        daytrade = berechne_daytrade_signal(levels, ind, aktuell, richtung, hoch, tief,
                                             wkeit, intraday,
                                             kerzen_muster=kerzen_muster,
                                             chart_muster=chart_muster,
                                             tagesvol_pct=tagesvol_pct)

        # Chart (nur wenn benötigt)
        if mit_chart:
            chart_json = erstelle_chart(df, levels, zonen, hoch, tief, richtung, ticker,
                                         intraday, ema200_daily,
                                         kerzen_muster=kerzen_muster,
                                         chart_muster=chart_muster)
        else:
            chart_json = None

        # Tagesveränderung
        change_abs = aktuell - ind['vortag']
        change_pct = change_abs / ind['vortag'] * 100 if ind['vortag'] else 0

        # Zeitstempel: Stand der letzten Kerze + Zeitpunkt dieser Analyse (Europa/Berlin)
        datenstand = _fmt_zeit(df.index[-1])
        abgerufen  = _jetzt_berlin()

        # Levels für Tabelle aufbereiten (sortiert nach Preis, mit Typ)
        alle_levels = []
        for name_l, preis in sorted(levels.items(), key=lambda x: x[1], reverse=True):
            abstand = (preis - aktuell) / aktuell * 100
            typ = 'resistance' if preis > aktuell else ('support' if preis < aktuell else 'aktuell')
            alle_levels.append({
                'name':    name_l,
                'preis':   preis,
                'abstand': abstand,
                'typ':     typ,
                'farbe':   FIB_FARBEN.get(name_l, '#888'),
            })

        return {
            'ticker':          ticker.upper(),
            'name':            name,
            'waehrung':        waehrung,
            'waehrung_symbol': waehrung_symbol,
            'periode':         PERIODEN.get(periode, PERIODEN['1y'])['label'],
            'datenstand':      datenstand,
            'abgerufen':       abgerufen,
            'tagesvol_pct':    tagesvol_pct,
            'aktuell':         aktuell,
            'change_abs':      change_abs,
            'change_pct':      change_pct,
            'hoch':            hoch,
            'tief':            tief,
            'richtung':        richtung,
            'swing_spanne':    hoch - tief,
            'wahrscheinlichkeit_bullisch': wkeit,
            'wahrscheinlichkeit_baerisch': round(100 - wkeit, 1),
            'faktoren':    faktoren,
            'support':     round(support,    2) if support    is not None else round(tief, 2),
            'resistance':  round(resistance, 2) if resistance is not None else round(hoch, 2),
            'levels':      alle_levels,
            'zonen':       zonen,
            'indikatoren': {
                'rsi':           ind['rsi'],
                'ema20':         round(ind['ema20'],  2),
                'ema50':         round(ind['ema50'],  2),
                'ema200':        round(ind['ema200'], 2),
                'macd':          round(ind['macd'],   4),
                'macd_signal':   round(ind['macd_signal'], 4),
                'atr':           round(ind['atr'],    2),
                'hoch52w':       ind['hoch52w'],
                'tief52w':       ind['tief52w'],
                'volumen_ratio': round(ind['volumen_ratio'], 2),
                'adx':           ind.get('adx', 0),
                'plus_di':       ind.get('plus_di', 0),
                'minus_di':      ind.get('minus_di', 0),
                'vwap':          ind.get('vwap', 0),
                'bb_upper':      ind.get('bb_upper', 0),
                'bb_lower':      ind.get('bb_lower', 0),
                'bb_mid':        ind.get('bb_mid', 0),
                'bb_pos':        round(ind.get('bb_pos', 0.5), 3),
                'bb_breite':     ind.get('bb_breite', 0),
                'stoch_k':       ind.get('stoch_k', 50),
                'stoch_d':       ind.get('stoch_d', 50),
            },
            'chart_json':    chart_json,
            'signal':        signal,
            'daytrade':      daytrade,
            'kerzen_muster': kerzen_muster,
            'chart_muster':  chart_muster,
            'fehler':        None,
        }
    except Exception as e:
        return {'fehler': f'Analyse fehlgeschlagen: {str(e)}'}
