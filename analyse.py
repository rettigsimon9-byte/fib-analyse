import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json

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

def berechne_indikatoren(df: pd.DataFrame):
    close = df['Close']
    indikatoren = {}

    # EMAs
    indikatoren['ema20']  = close.ewm(span=20,  adjust=False).mean().iloc[-1]
    indikatoren['ema50']  = close.ewm(span=50,  adjust=False).mean().iloc[-1]
    indikatoren['ema200'] = close.ewm(span=200, adjust=False).mean().iloc[-1]

    # RSI (14)
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(com=13, adjust=False).mean().iloc[-1]
    if avg_loss == 0:
        indikatoren['rsi'] = 100.0
    else:
        rs = avg_gain / avg_loss
        indikatoren['rsi'] = round(100 - (100 / (1 + rs)), 1)

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line   = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    indikatoren['macd']        = macd_line.iloc[-1]
    indikatoren['macd_signal'] = signal_line.iloc[-1]
    indikatoren['macd_hist']   = macd_line.iloc[-1] - signal_line.iloc[-1]

    # Volumen-Trend (letzter Kerzen-Schnitt vs. 20-Periode-Schnitt)
    vol_avg = df['Volume'].rolling(20).mean().iloc[-1]
    vol_letzt = df['Volume'].iloc[-1]
    indikatoren['volumen_ratio'] = vol_letzt / vol_avg if vol_avg > 0 else 1.0

    # ATR (14) für Volatilität
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low']  - df['Close'].shift()).abs(),
    ], axis=1).max(axis=1)
    indikatoren['atr'] = tr.rolling(14).mean().iloc[-1]

    indikatoren['aktuell'] = close.iloc[-1]
    indikatoren['vortag']  = close.iloc[-2] if len(close) > 1 else close.iloc[-1]
    indikatoren['hoch52w'] = df['High'].rolling(min(252, len(df))).max().iloc[-1]
    indikatoren['tief52w'] = df['Low'].rolling(min(252, len(df))).min().iloc[-1]

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

    # ── 3. RSI-Analyse ────────────────────────────────────────────────────────
    rsi = ind['rsi']
    if rsi < 25:
        score += 20
        faktoren.append({'text': f'RSI stark überverkauft ({rsi:.0f}) – Bounce wahrscheinlich', 'wert': '+20', 'farbe': 'success'})
    elif rsi < 35:
        score += 12
        faktoren.append({'text': f'RSI überverkauft ({rsi:.0f})', 'wert': '+12', 'farbe': 'success'})
    elif rsi < 45:
        score += 4
        faktoren.append({'text': f'RSI leicht bärisch ({rsi:.0f})', 'wert': '+4', 'farbe': 'secondary'})
    elif rsi > 75:
        score -= 20
        faktoren.append({'text': f'RSI stark überkauft ({rsi:.0f}) – Rücksetzer wahrscheinlich', 'wert': '−20', 'farbe': 'danger'})
    elif rsi > 65:
        score -= 12
        faktoren.append({'text': f'RSI überkauft ({rsi:.0f})', 'wert': '−12', 'farbe': 'danger'})
    elif rsi > 55:
        score -= 4
        faktoren.append({'text': f'RSI leicht bullisch ({rsi:.0f})', 'wert': '−4', 'farbe': 'secondary'})

    # ── 4. MACD ───────────────────────────────────────────────────────────────
    hist = ind['macd_hist']
    macd = ind['macd']
    sig  = ind['macd_signal']
    if macd > sig and hist > 0:
        score += 8
        faktoren.append({'text': 'MACD bullisches Kreuz (über Signallinie)', 'wert': '+8', 'farbe': 'success'})
    elif macd < sig and hist < 0:
        score -= 8
        faktoren.append({'text': 'MACD bärisches Kreuz (unter Signallinie)', 'wert': '−8', 'farbe': 'danger'})

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
                   intraday: bool = False):

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

    # ── Subplots anlegen ─────────────────────────────────────────────────────
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.55, 0.15, 0.15, 0.15],
    )

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

    # Fibonacci-Levels — Labels versetzt damit sie sich nicht überlappen
    sorted_levels = sorted(levels.items(), key=lambda x: x[1])
    prev_price   = None
    xshift_idx   = 0
    xshift_stufen = [0, 75, 150]  # 3 horizontale Positionen zum Ausweichen

    for name, preis in sorted_levels:
        farbe = FIB_FARBEN.get(name, '#888888')
        ist_extension = any(x in name for x in ['127', '138', '161', '200', '261'])

        # Wenn Level zu nah am vorherigen → Label nach rechts verschieben
        if prev_price and abs(preis - prev_price) / max(prev_price, 1e-9) < 0.005:
            xshift_idx = (xshift_idx + 1) % len(xshift_stufen)
        else:
            xshift_idx = 0

        fig.add_hline(
            y=preis, row=1, col=1,
            line=dict(color=farbe, width=1.2 if not ist_extension else 0.8,
                      dash='solid' if not ist_extension else 'dash'),
            annotation_text=f'{name}  {preis:.2f}',
            annotation_position='right',
            annotation_xshift=xshift_stufen[xshift_idx],
            annotation_font=dict(size=9, color=farbe),
        )
        prev_price = preis

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
        yaxis =dict(gridcolor='#1e293b', showgrid=True, side='right'),
        yaxis2=dict(gridcolor='#1e293b', showgrid=True, side='right',
                    title=dict(text='Vol', font=dict(size=9, color='#64748b'))),
        yaxis3=dict(gridcolor='#1e293b', showgrid=True, side='right',
                    range=[0, 100],
                    title=dict(text='RSI', font=dict(size=9, color='#a78bfa'))),
        yaxis4=dict(gridcolor='#1e293b', showgrid=True, side='right',
                    title=dict(text='MACD', font=dict(size=9, color='#3b82f6'))),
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

# ── Handelssignal Algorithmus ─────────────────────────────────────────────────

SIGNAL_TEXTE = {
    'KAUFEN':      '🟢 KAUFSIGNAL',
    'BEOBACHTEN':  '🟡 BEOBACHTEN',
    'WARTEN':      '⚪ ABWARTEN',
    'VORSICHT':    '🟠 VORSICHT',
    'MEIDEN':      '🔴 MEIDEN',
}

SIGNAL_FARBEN = {
    'KAUFEN':     'success',
    'BEOBACHTEN': 'warning',
    'WARTEN':     'secondary',
    'VORSICHT':   'orange',
    'MEIDEN':     'danger',
}

KEY_FIB_LEVELS = {'61,8 %', '50,0 %', '38,2 %', '23,6 %'}

def berechne_handelssignal(df, levels, ind, aktuell, richtung, hoch, tief):
    score        = 0
    begruendungen = []
    warnungen    = []
    bedingungen  = []

    alle_preise  = sorted(levels.values())
    supports     = sorted([p for p in alle_preise if p <= aktuell * 1.005], reverse=True)
    resistances  = sorted([p for p in alle_preise if p >= aktuell * 0.995])

    naechster_support    = supports[0]    if supports    else tief
    naechste_resistance  = resistances[0] if resistances else hoch

    atr    = ind['atr']
    rsi    = ind['rsi']
    ema20  = ind['ema20']
    ema50  = ind['ema50']
    ema200 = ind['ema200']
    macd   = ind['macd']
    msig   = ind['macd_signal']
    mhist  = ind['macd_hist']
    vr     = ind['volumen_ratio']

    # ── 1. Fibonacci-Support-Nähe ─────────────────────────────────────────────
    abstand_support_pct    = (aktuell - naechster_support)   / aktuell * 100
    abstand_resist_pct     = (naechste_resistance - aktuell) / aktuell * 100

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

    # ── 2. Trend (EMA-Struktur) ───────────────────────────────────────────────
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
        begruendungen.append('EMA-Fächer bullisch ausgerichtet (EMA20 > EMA50 > EMA200)')
    elif ema20 < ema50 < ema200:
        score -= 8
        warnungen.append('EMA-Fächer bärisch ausgerichtet (EMA20 < EMA50 < EMA200)')

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

    # ── 4. MACD ───────────────────────────────────────────────────────────────
    if macd > msig and mhist > 0:
        score += 12
        begruendungen.append('MACD über Signallinie – bullisches Momentum')
    elif macd < msig and mhist < 0:
        score -= 10
        warnungen.append('MACD unter Signallinie – bärisches Momentum')

    # MACD dreht gerade bullisch (Kreuz in letzten 3 Perioden)
    if abs(mhist) < atr * 0.05 and macd > msig:
        score += 8
        begruendungen.append('Frisches MACD-Kaufkreuz erkannt')

    # ── 5. Volumen ────────────────────────────────────────────────────────────
    if vr >= 2.0:
        score += 12
        begruendungen.append(f'Sehr hohes Volumen ({vr:.1f}x Durchschnitt) – starke Bestätigung')
    elif vr >= 1.4:
        score += 6
        begruendungen.append(f'Überdurchschnittliches Volumen ({vr:.1f}x)')

    # ── 6. RSI-Divergenz ──────────────────────────────────────────────────────
    divergenz = erkenne_rsi_divergenz(df)
    if divergenz == 'bullisch':
        score += 18
        begruendungen.append('Bullische RSI-Divergenz: Preis tieferes Tief, RSI höheres Tief → Trendwende-Signal')
    elif divergenz == 'bärisch':
        score -= 16
        warnungen.append('Bärische RSI-Divergenz: Preis höheres Hoch, RSI tieferes Hoch → Schwäche-Signal')

    # ── 7. Kerzenformation ────────────────────────────────────────────────────
    formation = erkenne_kerzenformation(df)
    formation_texte = {
        'hammer':               ('Hammer-Kerze erkannt – bullisches Umkehrsignal', +12),
        'bullisches_engulfing': ('Bullisches Engulfing – starkes Kaufsignal', +15),
        'baerisches_engulfing': ('Bärisches Engulfing – Verkaufsdruck', -14),
        'morgenstern':          ('Morgenstern-Formation – bullische Trendwende', +18),
        'doji':                 ('Doji-Kerze – Unentschlossenheit am Markt', 0),
    }
    if formation and formation in formation_texte:
        text, punkte = formation_texte[formation]
        score += punkte
        if punkte > 0:
            begruendungen.append(text)
        elif punkte < 0:
            warnungen.append(text)
        else:
            bedingungen.append(text)

    # ── 8. Swing-Richtung ─────────────────────────────────────────────────────
    if richtung == 'aufwärts':
        score += 5
    else:
        score -= 5
        warnungen.append('Primärer Swing zeigt Abwärts – erhöhtes Rückschlagrisiko')

    # ── Signal-Typ ────────────────────────────────────────────────────────────
    if   score >= 60:  typ = 'KAUFEN'
    elif score >= 35:  typ = 'BEOBACHTEN'
    elif score >= 10:  typ = 'WARTEN'
    elif score >= -10: typ = 'VORSICHT'
    else:              typ = 'MEIDEN'

    staerke = max(5, min(95, int(score * 0.9 + 50)))

    # ── Einstiegskurs ─────────────────────────────────────────────────────────
    if abstand_support_pct <= 2.5 and score >= 35:
        einstieg = aktuell
        bedingungen.insert(0, 'Einstieg jetzt zum aktuellen Kurs möglich')
    elif score >= 35:
        einstieg = naechster_support * 1.005
        bedingungen.insert(0, f'Auf Rücksetzer zum Support {naechster_support:.2f} warten, dann einsteigen')
    else:
        einstieg = aktuell
        bedingungen.insert(0, 'Kein klares Kaufsignal – besser abwarten')

    # ── Stop-Loss ─────────────────────────────────────────────────────────────
    # 1× ATR unter dem nächsten Support – dynamisch an Volatilität angepasst
    stop_loss     = naechster_support - (atr * 1.2)
    stop_loss_pct = (einstieg - stop_loss) / einstieg * 100 if einstieg > 0 else 5.0

    # Mindest-SL 1.5%, Maximum 12%
    if stop_loss_pct < 1.5:
        stop_loss     = einstieg * 0.985
        stop_loss_pct = 1.5
    elif stop_loss_pct > 12:
        stop_loss     = einstieg * 0.88
        stop_loss_pct = 12.0

    # ── Kursziele ─────────────────────────────────────────────────────────────
    ziele_preise = sorted([p for p in alle_preise if p > einstieg * 1.005])

    # Mindestens 3 Ziele sicherstellen (notfalls mit ATR-Vielfachen auffüllen)
    while len(ziele_preise) < 3:
        letztes = ziele_preise[-1] if ziele_preise else einstieg
        ziele_preise.append(round(letztes + atr * 3, 2))

    ziel_1, ziel_2, ziel_3 = ziele_preise[0], ziele_preise[1], ziele_preise[2]

    def pct(ziel): return round((ziel - einstieg) / einstieg * 100, 1)
    def rr(ziel):  return round(pct(ziel) / stop_loss_pct, 1) if stop_loss_pct > 0 else 0

    z1_pct, z2_pct, z3_pct = pct(ziel_1), pct(ziel_2), pct(ziel_3)
    rr1,    rr2,    rr3    = rr(ziel_1),  rr(ziel_2),  rr(ziel_3)

    # ── Eintrittsbedingungen / Handlungsempfehlung ────────────────────────────
    if typ == 'KAUFEN':
        bedingungen.append(f'Stop-Loss zwingend bei {stop_loss:.2f} setzen (−{stop_loss_pct:.1f}%)')
        bedingungen.append(f'Empfehlung: Bei Ziel 1 ({ziel_1:.2f}) 40% verkaufen, Rest laufen lassen')
        if rr2 >= 2:
            bedingungen.append(f'Chancen/Risiko bei Ziel 2: {rr2}:1 – sehr attraktiv')
    elif typ == 'BEOBACHTEN':
        bedingungen.append('Warte auf weitere Bestätigung (grüne Tageskerze, RSI-Anstieg)')
        bedingungen.append('Keinen Kauf ohne Bestätigung – zu früh einsteigen kostet Performance')
    elif typ in ('VORSICHT', 'MEIDEN'):
        bedingungen.append('Kein Kauf empfehlenswert – besser auf bessere Einstiegsgelegenheit warten')
        bedingungen.append('Bestehende Positionen mit Stop-Loss absichern')

    return {
        'typ':           typ,
        'text':          SIGNAL_TEXTE[typ],
        'farbe':         SIGNAL_FARBEN[typ],
        'staerke':       staerke,
        'score':         score,
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
        'support':       round(naechster_support,   2),
        'resistance':    round(naechste_resistance, 2),
    }

# ── Haupt-Analyse-Funktion ────────────────────────────────────────────────────

def analysiere(ticker: str, periode: str = '1y'):
    cfg = PERIODEN.get(periode, PERIODEN['1y'])
    df, name, waehrung, fehler = lade_daten(ticker, periode)
    if fehler:
        return {'fehler': fehler}
    waehrung_symbol = WAEHRUNG_SYMBOLE.get(waehrung, waehrung)

    # Technische Indikatoren
    ind = berechne_indikatoren(df)
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

    # Chart
    intraday = cfg.get('intraday', False)
    chart_json = erstelle_chart(df, levels, zonen, hoch, tief, richtung, ticker, intraday)

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
        'ticker':         ticker.upper(),
        'name':           name,
        'waehrung':       waehrung,
        'waehrung_symbol': waehrung_symbol,
        'periode':        PERIODEN.get(periode, PERIODEN['1y'])['label'],
        'aktuell':        aktuell,
        'change_abs':  change_abs,
        'change_pct':  change_pct,
        'hoch':        hoch,
        'tief':        tief,
        'richtung':    richtung,
        'swing_spanne': hoch - tief,
        'wahrscheinlichkeit_bullisch': wkeit,
        'wahrscheinlichkeit_baerisch': round(100 - wkeit, 1),
        'faktoren':    faktoren,
        'support':     support,
        'resistance':  resistance,
        'levels':      alle_levels,
        'zonen':       zonen,
        'indikatoren': {
            'rsi':    ind['rsi'],
            'ema20':  round(ind['ema20'],  2),
            'ema50':  round(ind['ema50'],  2),
            'ema200': round(ind['ema200'], 2),
            'macd':   round(ind['macd'],   4),
            'macd_signal': round(ind['macd_signal'], 4),
            'atr':    round(ind['atr'],    2),
            'hoch52w': ind['hoch52w'],
            'tief52w': ind['tief52w'],
            'volumen_ratio': round(ind['volumen_ratio'], 2),
        },
        'chart_json':  chart_json,
        'signal':      signal,
        'fehler':      None,
    }
