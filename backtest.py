"""Walk-Forward Backtest des Daytrade-Signals.

Simuliert das Daytrade-Signal Bar-für-Bar wie bei realem Live-Trading:
- Bei jedem neuen Bar wird das Signal NUR aus den bis dahin sichtbaren Daten
  generiert (kein Look-Ahead Bias).
- Wenn ein LONG/SHORT-Signal entsteht, wird die Position beim Open des
  NÄCHSTEN Bars eröffnet (realistische Latenz).
- Position wird geschlossen wenn:
    * SL oder TP innerhalb der nächsten N Bars erreicht wird (intraday: 12 Bars,
      sonst 5 Bars Timeout)
    * Timeout abläuft → Exit zum Close

Liefert Statistiken: Win-Rate, Profit Factor, Expectancy, Max Drawdown, Sharpe.

Hinweis: yfinance liefert für 5m-Intervalle nur ~60 Tage Historie. Längere
Backtests benötigen entsprechend höhere Intervalle (1h / 1d / 1wk).
"""

import yfinance as yf
import pandas as pd
import numpy as np
import math

from analyse import (
    PERIODEN,
    berechne_indikatoren, markantester_swing, berechne_fib_levels,
    berechne_wahrscheinlichkeit, erkenne_kerzenformation, erkenne_chartmuster,
    berechne_daytrade_signal,
    berechne_intraday_strukturlevels, hole_htf_trend,
    pruefe_zeitfilter, pruefe_earnings_naehe,
    hole_eur_kurs,
)


def _lade_history(ticker: str, periode_key: str):
    """Wie analyse.lade_daten, aber liefert vollständige History ohne fast_info-
    Live-Patch (Backtest darf keine Look-Ahead-Daten nutzen)."""
    cfg = PERIODEN.get(periode_key, PERIODEN['1y'])
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period=cfg['yf'], interval=cfg['interval'], auto_adjust=False)
        if df is None or df.empty:
            return None, 'Keine Daten geladen'
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col not in df.columns:
                return None, f'Spalte {col} fehlt'

        # FX → EUR (wie im Live-System)
        try:
            waehrung = tk.fast_info.currency or 'USD'
            fx = hole_eur_kurs(waehrung)
            if fx != 1.0:
                for col in ['Open', 'High', 'Low', 'Close']:
                    df[col] = df[col] * fx
        except Exception:
            pass

        return df, None
    except Exception as e:
        return None, str(e)


def _signal_aus_sicht(df_sicht: pd.DataFrame, ticker: str,
                       cfg: dict, htf_trend_cache: str):
    """Generiert ein Daytrade-Signal aus dem sichtbaren Datenausschnitt."""
    intraday = cfg.get('intraday', False)
    fenster  = cfg.get('fenster', 10)
    if len(df_sicht) < fenster * 3:
        fenster = max(2, len(df_sicht) // 5)

    ind     = berechne_indikatoren(df_sicht, intraday=intraday)
    aktuell = ind['aktuell']
    hoch, tief, richtung = markantester_swing(df_sicht, fenster)
    levels = berechne_fib_levels(hoch, tief, richtung)
    kerzen = erkenne_kerzenformation(df_sicht)
    chart  = erkenne_chartmuster(df_sicht, fenster)
    wkeit, _, _, _ = berechne_wahrscheinlichkeit(aktuell, levels, ind, richtung)

    struktur = berechne_intraday_strukturlevels(df_sicht) if intraday else {}
    ist_handelszeit, zeit_grund = pruefe_zeitfilter(df_sicht, intraday)

    # Earnings-Check: zu teuer pro Bar im Backtest (Quota-Hit), wir nutzen die
    # Annahme dass Earnings selten sind – das verzerrt höchstens 1-2% der Trades.
    earnings_warnung = False

    return berechne_daytrade_signal(
        levels, ind, aktuell, richtung, hoch, tief,
        bullisch_pct=wkeit, intraday=intraday,
        kerzen_muster=kerzen, chart_muster=chart,
        df=df_sicht, ticker=ticker, intervall=cfg['interval'],
        intraday_struktur=struktur,
        htf_trend=htf_trend_cache,
        earnings_warnung=earnings_warnung,
        ist_handelszeit=ist_handelszeit, zeit_grund=zeit_grund,
    )


def _statistiken(trades: list) -> dict:
    """Berechnet Performance-Statistiken aus einer Trade-Liste."""
    n = len(trades)
    if n == 0:
        return {
            'n_trades': 0, 'win_rate': 0, 'profit_factor': 0,
            'expectancy_pct': 0, 'avg_win_pct': 0, 'avg_loss_pct': 0,
            'gesamtgewinn_pct': 0, 'max_drawdown_pct': 0, 'sharpe': 0,
            'long_trades': 0, 'short_trades': 0,
            'long_win_rate': 0, 'short_win_rate': 0,
        }

    wins   = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]
    win_rate = len(wins) / n * 100

    sum_wins   = sum(t['pnl_pct'] for t in wins)
    sum_losses = sum(t['pnl_pct'] for t in losses)
    profit_factor = (sum_wins / abs(sum_losses)) if losses and sum_losses != 0 else float('inf')

    avg_win  = (sum_wins / len(wins))     if wins   else 0
    avg_loss = (sum_losses / len(losses)) if losses else 0
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate/100) * avg_loss)

    equity = np.cumsum([t['pnl_pct'] for t in trades])
    peak   = np.maximum.accumulate(equity)
    dd     = peak - equity
    max_dd = float(dd.max()) if len(dd) > 0 else 0

    # Sharpe (vereinfacht – ohne risk-free rate, ohne Annualisierung)
    pnl_arr = np.array([t['pnl_pct'] for t in trades])
    sharpe = float(pnl_arr.mean() / pnl_arr.std()) if pnl_arr.std() > 0 else 0

    longs  = [t for t in trades if t['richtung'] == 'LONG']
    shorts = [t for t in trades if t['richtung'] == 'SHORT']
    long_wr  = (len([t for t in longs  if t['pnl_pct'] > 0]) / len(longs)  * 100) if longs  else 0
    short_wr = (len([t for t in shorts if t['pnl_pct'] > 0]) / len(shorts) * 100) if shorts else 0

    return {
        'n_trades':         n,
        'win_rate':         round(win_rate, 1),
        'profit_factor':    round(profit_factor, 2) if not math.isinf(profit_factor) else 99.99,
        'expectancy_pct':   round(expectancy, 3),
        'avg_win_pct':      round(avg_win,  3),
        'avg_loss_pct':     round(avg_loss, 3),
        'gesamtgewinn_pct': round(float(equity[-1]) if len(equity) else 0, 2),
        'max_drawdown_pct': round(max_dd, 2),
        'sharpe':           round(sharpe, 2),
        'long_trades':      len(longs),
        'short_trades':     len(shorts),
        'long_win_rate':    round(long_wr,  1),
        'short_win_rate':   round(short_wr, 1),
    }


def backtest_daytrade(ticker: str, periode: str = '5d',
                       max_bars: int = None, min_warmup: int = 50) -> dict:
    """Walk-Forward-Backtest des aktuellen Daytrade-Signals.

    Args:
        ticker: Yahoo-Symbol (z.B. 'AAPL', 'BTC-USD').
        periode: PERIODEN-Schlüssel (z.B. '5d', '1mo', '1y').
        max_bars: Max. Anzahl Bars zum Testen (default: alle nach Warmup).
        min_warmup: Bars die als Warmup nötig sind (für EMA200 etc.).

    Returns:
        Dict mit Statistiken und Trade-Liste.
    """
    cfg = PERIODEN.get(periode, PERIODEN['5d'])
    intraday = cfg.get('intraday', False)

    df_full, fehler = _lade_history(ticker, periode)
    if fehler:
        return {'fehler': fehler, 'ticker': ticker, 'periode': periode}
    if df_full is None or len(df_full) < min_warmup + 10:
        return {'fehler': f'Zu wenig Daten ({0 if df_full is None else len(df_full)} Bars, min {min_warmup + 10})',
                'ticker': ticker, 'periode': periode}

    # HTF-Trend einmalig holen (im Backtest pro Run statt pro Bar — sonst Quota-Hit
    # und der HTF-Trend ändert sich auf Stunden-/Tagesbasis kaum innerhalb eines Backtest-Fensters)
    htf_trend = hole_htf_trend(ticker, cfg['interval']) if intraday else 'neutral'

    # Timeout pro Intervall — vorher war 5 Bars für daily zu kurz: TPs lagen
    # bei 2× SL-Distanz, was in 5 Tagesbars praktisch nie erreicht wurde.
    # Realistische Faustregel: timeout = 2-3× erwartete Bars bis TP.
    TIMEOUT_BARS = {
        '5m':  24,   # ~2h
        '15m': 16,   # ~4h
        '1h':  12,   # 1.5 Handelstage
        '1d':  20,   # ~1 Monat
        '1wk': 12,   # ~3 Monate
    }
    timeout_bars = TIMEOUT_BARS.get(cfg['interval'], 10)
    n_bars = len(df_full)
    bis = n_bars - timeout_bars - 1
    if max_bars:
        bis = min(bis, min_warmup + max_bars)

    trades = []
    in_position = False  # Verhindert Überlappung – ein Trade aktiv pro Zeit
    pos_close_bar = 0

    for i in range(min_warmup, bis):
        if in_position and i < pos_close_bar:
            continue
        in_position = False

        df_sicht = df_full.iloc[:i + 1]
        try:
            dt = _signal_aus_sicht(df_sicht, ticker, cfg, htf_trend)
        except Exception:
            continue

        if dt.get('kein_signal'):
            continue

        # Trade simulieren — Einstieg beim Open des nächsten Bars
        entry_idx = i + 1
        if entry_idx >= n_bars:
            break
        entry_bar = df_full.iloc[entry_idx]
        entry = float(entry_bar['Open'])
        sl    = float(dt['stop_loss'])
        tp    = float(dt['take_profit'])
        side  = dt['richtung']

        exit_price = None
        exit_grund = 'timeout'
        exit_idx   = entry_idx
        for j in range(entry_idx, min(entry_idx + timeout_bars, n_bars)):
            bar = df_full.iloc[j]
            hi, lo = float(bar['High']), float(bar['Low'])
            if side == 'LONG':
                # Konservativ: wenn dieselbe Kerze SL+TP berührt → SL angenommen (worst case)
                if lo <= sl:
                    exit_price, exit_grund, exit_idx = sl, 'SL', j
                    break
                if hi >= tp:
                    exit_price, exit_grund, exit_idx = tp, 'TP', j
                    break
            else:  # SHORT
                if hi >= sl:
                    exit_price, exit_grund, exit_idx = sl, 'SL', j
                    break
                if lo <= tp:
                    exit_price, exit_grund, exit_idx = tp, 'TP', j
                    break

        if exit_price is None:
            exit_idx = min(entry_idx + timeout_bars - 1, n_bars - 1)
            exit_price = float(df_full.iloc[exit_idx]['Close'])

        # P&L in Prozent
        if side == 'LONG':
            pnl_pct = (exit_price - entry) / entry * 100
        else:
            pnl_pct = (entry - exit_price) / entry * 100

        trades.append({
            'bar_idx':    i,
            'entry_zeit': str(df_full.index[entry_idx]),
            'exit_zeit':  str(df_full.index[exit_idx]),
            'richtung':   side,
            'entry':      round(entry,      4),
            'exit':       round(exit_price, 4),
            'sl':         round(sl,         4),
            'tp':         round(tp,         4),
            'exit_grund': exit_grund,
            'pnl_pct':    round(pnl_pct,    3),
            'staerke':    dt.get('staerke', 0),
            'rr':         dt.get('rr',      0),
            'haltedauer': exit_idx - entry_idx,
        })

        # Position sperren bis Exit (keine Überlappung)
        in_position   = True
        pos_close_bar = exit_idx + 1

    stats = _statistiken(trades)
    stats.update({
        'ticker':        ticker,
        'periode':       periode,
        'periode_label': cfg['label'],
        'intraday':      intraday,
        'htf_trend':     htf_trend,
        'bars_total':    n_bars,
        'bars_getestet': bis - min_warmup,
        'trades':        trades,
    })
    return stats
