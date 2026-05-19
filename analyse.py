import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import time

_fx_cache: dict = {}
_FX_TTL = 3600  # 1 Stunde


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

WAEHRUNG_SYMBOLE = {
    'EUR': '€', 'USD': '$', 'GBP': '£', 'CHF': 'CHF',
    'JPY': '¥', 'CAD': 'CA$', 'AUD': 'A$', 'HKD': 'HK$',
    'CNY': '¥', 'SEK': 'kr', 'NOK': 'kr', 'DKK': 'kr',
}

# ── Datenabruf ────────────────────────────────────────────────────────────────

def lade_daten(ticker: str, periode: str = '1y'):
    cfg = PERIODEN.get(periode, PERIODEN['1y'])
    try:
        tk = yf.Ticker(ticker)

        # auto_adjust=False → echte Marktpreise, keine dividendenbereinigten Kurse
        df = tk.history(period=cfg['yf'], interval=cfg['interval'], auto_adjust=False)
        if df.empty:
            return None, None, 'USD', f'Kein Ticker "{ticker}" gefunden.'

        # MultiIndex bereinigen (tritt bei manchen yfinance-Versionen auf)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

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
                   intraday: bool = False, ema200_daily: float = None):

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

def erkenne_kerzenformation(df: pd.DataFrame):
    if len(df) < 3:
        return None

    c1 = df.iloc[-3]  # vorvorletzte Kerze
    c2 = df.iloc[-2]  # vorletzte Kerze
    c3 = df.iloc[-1]  # letzte Kerze

    o, h, l, c = c3['Open'], c3['High'], c3['Low'], c3['Close']
    body         = abs(c - o)
    gesamtrange  = h - l
    if gesamtrange < 1e-9:
        return None
    upper_wick   = h - max(c, o)
    lower_wick   = min(c, o) - l

    # Hammer: kleiner Körper oben, langer unterer Schatten (bullisch)
    if (lower_wick >= body * 2.0 and
            upper_wick <= body * 0.5 and
            body / gesamtrange <= 0.35):
        return 'hammer'

    # Bullisches Engulfing: letzte Kerze umschließt vorherige rote Kerze
    if (c > o and c2['Close'] < c2['Open'] and
            o < c2['Close'] and c > c2['Open']):
        return 'bullisches_engulfing'

    # Bärisches Engulfing
    if (c < o and c2['Close'] > c2['Open'] and
            o > c2['Close'] and c < c2['Open']):
        return 'baerisches_engulfing'

    # Morgenstern (3 Kerzen): rot → kleiner Körper → große grüne Kerze
    body1 = abs(c1['Close'] - c1['Open'])
    body2 = abs(c2['Close'] - c2['Open'])
    body3 = body
    if (c1['Close'] < c1['Open'] and
            body2 <= body1 * 0.4 and
            c > o and body3 >= body1 * 0.5 and
            c > (c1['Open'] + c1['Close']) / 2):
        return 'morgenstern'

    # Doji: Körper sehr klein → Unentschlossenheit
    if body <= gesamtrange * 0.08:
        return 'doji'

    return None

# ── Daytrading Signal ────────────────────────────────────────────────────────

def berechne_daytrade_signal(levels: dict, ind: dict, aktuell: float,
                              richtung: str, hoch: float, tief: float,
                              bullisch_pct: float = 50.0):
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

    alle_preise = sorted(levels.values())
    supports    = sorted([p for p in alle_preise if p < aktuell * 0.9995], reverse=True)
    resistances = sorted([p for p in alle_preise if p > aktuell * 1.0005])

    naechster_support   = supports[0]    if supports    else tief
    naechste_resistance = resistances[0] if resistances else hoch

    abstand_sup_pct = (aktuell - naechster_support)   / aktuell * 100
    abstand_res_pct = (naechste_resistance - aktuell) / aktuell * 100

    long_score  = 0
    short_score = 0
    gruende_long  = []
    gruende_short = []

    # RSI
    if rsi < 30:
        long_score += 3;  gruende_long.append(f'RSI stark überverkauft ({rsi:.0f})')
    elif rsi < 45:
        long_score += 1;  gruende_long.append(f'RSI überverkauft ({rsi:.0f})')
    elif rsi > 70:
        short_score += 3; gruende_short.append(f'RSI stark überkauft ({rsi:.0f})')
    elif rsi > 55:
        short_score += 1; gruende_short.append(f'RSI leicht überkauft ({rsi:.0f})')

    # MACD (echtes Kreuz)
    if mhist > 0 and mhist_p <= 0:
        long_score += 3;  gruende_long.append('Frisches MACD-Kaufkreuz')
    elif macd > msig:
        long_score += 2;  gruende_long.append('MACD bullisches Momentum')
    elif mhist < 0 and mhist_p >= 0:
        short_score += 3; gruende_short.append('Frisches MACD-Verkaufskreuz')
    else:
        short_score += 2; gruende_short.append('MACD bärisches Momentum')

    # EMA-Trend
    if aktuell > ema20 > ema50:
        long_score += 2;  gruende_long.append('Aufwärtstrend (Preis > EMA20 > EMA50)')
    elif aktuell < ema20 < ema50:
        short_score += 2; gruende_short.append('Abwärtstrend (Preis < EMA20 < EMA50)')

    # Fibonacci-Position
    if abstand_sup_pct < abstand_res_pct and abstand_sup_pct < 1.5:
        long_score += 2;  gruende_long.append(f'Nah am Fib-Support ({naechster_support:.2f})')
    elif abstand_res_pct < abstand_sup_pct and abstand_res_pct < 1.5:
        short_score += 2; gruende_short.append(f'Nah am Fib-Widerstand ({naechste_resistance:.2f})')

    # VWAP – stärkster Intraday-Filter
    if vwap > 0:
        if aktuell > vwap * 1.002:
            long_score += 3;  gruende_long.append(f'Über VWAP ({vwap:.2f}) – bullische Bias')
        elif aktuell < vwap * 0.998:
            short_score += 3; gruende_short.append(f'Unter VWAP ({vwap:.2f}) – bärische Bias')

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
        long_score += 2;  gruende_long.append(f'Stochastic dreht aufwärts aus überverkaufter Zone ({sk:.0f})')
    elif sk < 20:
        long_score += 1;  gruende_long.append(f'Stochastic überverkauft ({sk:.0f})')
    elif sk > 80 and sk < sk_p:
        short_score += 2; gruende_short.append(f'Stochastic dreht abwärts aus überkaufter Zone ({sk:.0f})')
    elif sk > 80:
        short_score += 1; gruende_short.append(f'Stochastic überkauft ({sk:.0f})')

    # Swing-Richtung
    if richtung == 'aufwärts': long_score  += 1
    else:                      short_score += 1

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

    # ── Preisziele ────────────────────────────────────────────────────────────
    if dt_richtung == 'LONG':
        take_profit = naechste_resistance
        stop_loss   = naechster_support - (atr * 0.5)
        tp_pct      = (take_profit - aktuell) / aktuell * 100
        sl_pct      = (aktuell - stop_loss)   / aktuell * 100
    else:
        take_profit = naechster_support
        stop_loss   = naechste_resistance + (atr * 0.5)
        tp_pct      = (aktuell - take_profit) / aktuell * 100
        sl_pct      = (stop_loss - aktuell)   / aktuell * 100

    # Minimaler Stop-Puffer (kein hartes Clipping nach oben)
    if sl_pct < 0.2:
        sl_pct = 0.5
        stop_loss = aktuell * (1 - sl_pct / 100) if dt_richtung == 'LONG' else aktuell * (1 + sl_pct / 100)

    tp_pct = max(0.2, tp_pct)
    rr = round(tp_pct / sl_pct, 1) if sl_pct > 0 else 0

    # ── Gates ────────────────────────────────────────────────────────────────
    kein_signal = abs(long_score - short_score) <= 1

    # R:R-Gate: mindestens 2:1
    if rr < 2.0:
        kein_signal = True

    # ADX-Gate: kein Signal bei extremem Range-Markt
    if adx < 12:
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

def berechne_handelssignal(df, levels, ind, aktuell, richtung, hoch, tief):
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

    # ── 7. Kerzenformation ────────────────────────────────────────────────────
    formation = erkenne_kerzenformation(df)
    formation_texte = {
        'hammer':               ('Hammer-Kerze – bullisches Umkehrsignal', +12),
        'bullisches_engulfing': ('Bullisches Engulfing – starkes Kaufsignal', +15),
        'baerisches_engulfing': ('Bärisches Engulfing – Verkaufsdruck', -14),
        'morgenstern':          ('Morgenstern-Formation – bullische Trendwende', +18),
        'doji':                 ('Doji-Kerze – Unentschlossenheit am Markt', 0),
    }
    if formation and formation in formation_texte:
        text, punkte = formation_texte[formation]
        score += punkte
        if punkte > 0:   begruendungen.append(text)
        elif punkte < 0: warnungen.append(text)
        else:            bedingungen.append(text)

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
        'formation':     formation,
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
    ema200_daily = None
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

        # Handelssignal
        signal = berechne_handelssignal(df, levels, ind, aktuell, richtung, hoch, tief)

        # Daytrading Signal
        daytrade = berechne_daytrade_signal(levels, ind, aktuell, richtung, hoch, tief, wkeit)

        # Chart (nur wenn benötigt)
        if mit_chart:
            chart_json = erstelle_chart(df, levels, zonen, hoch, tief, richtung, ticker,
                                         intraday, ema200_daily)
        else:
            chart_json = None

        # Tagesveränderung
        change_abs = aktuell - ind['vortag']
        change_pct = change_abs / ind['vortag'] * 100 if ind['vortag'] else 0

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
            'chart_json':  chart_json,
            'signal':      signal,
            'daytrade':    daytrade,
            'fehler':      None,
        }
    except Exception as e:
        return {'fehler': f'Analyse fehlgeschlagen: {str(e)}'}
