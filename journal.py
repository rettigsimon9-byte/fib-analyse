"""Trade-Journal: SQLite-Datenbank für gespeicherte Daytrade-Signale.

Speichert Trades per Knopfdruck und prüft automatisch ob SL oder TP
via yfinance erreicht wurde (Outcome: WIN / LOSS / TIMEOUT / OFFEN).
"""

import sqlite3
import os
import time
from datetime import datetime, timezone

import yfinance as yf

DB_PATH = os.path.join(os.path.dirname(__file__), 'journal.db')

# ── Schema ────────────────────────────────────────────────────────────────────

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with _conn() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                gespeichert TEXT    NOT NULL,
                ticker      TEXT    NOT NULL,
                periode     TEXT    NOT NULL,
                richtung    TEXT    NOT NULL,
                einstieg    REAL    NOT NULL,
                take_profit REAL    NOT NULL,
                stop_loss   REAL    NOT NULL,
                tp_pct      REAL    NOT NULL,
                sl_pct      REAL    NOT NULL,
                rr          REAL    NOT NULL,
                waehrung    TEXT    NOT NULL DEFAULT 'EUR',
                outcome     TEXT    NOT NULL DEFAULT 'OFFEN',
                exit_preis  REAL,
                exit_zeit   TEXT,
                pnl_pct     REAL,
                notiz       TEXT
            )
        ''')

# ── Trade speichern ───────────────────────────────────────────────────────────

def speichere_trade(ticker, periode, richtung, einstieg, take_profit,
                    stop_loss, tp_pct, sl_pct, rr, waehrung='EUR'):
    init_db()
    jetzt = datetime.now().strftime('%d.%m.%Y %H:%M')
    with _conn() as c:
        cur = c.execute('''
            INSERT INTO trades
              (gespeichert, ticker, periode, richtung, einstieg,
               take_profit, stop_loss, tp_pct, sl_pct, rr, waehrung)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ''', (jetzt, ticker.upper(), periode, richtung, einstieg,
              take_profit, stop_loss, tp_pct, sl_pct, rr, waehrung))
        return cur.lastrowid

# ── Outcome automatisch prüfen ────────────────────────────────────────────────

def _preis_seit(ticker: str, seit_str: str):
    """Holt High/Low seit dem Einstiegs-Zeitstempel (max. 5 Tage zurück)."""
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period='5d', interval='5m', auto_adjust=False)
        if df is None or df.empty:
            df = tk.history(period='5d', interval='15m', auto_adjust=False)
        if df is None or df.empty:
            return None, None

        # Filtern ab Einstiegszeit
        try:
            seit = datetime.strptime(seit_str, '%d.%m.%Y %H:%M')
            seit = seit.replace(tzinfo=timezone.utc)
            df = df[df.index >= seit]
        except Exception:
            pass

        if df.empty:
            return None, None
        return float(df['High'].max()), float(df['Low'].min())
    except Exception:
        return None, None

def pruefe_offene_trades():
    """Prüft alle offenen Trades gegen aktuelle Kursdaten. Gibt Anzahl Updates zurück."""
    init_db()
    updated = 0
    with _conn() as c:
        offene = c.execute(
            "SELECT * FROM trades WHERE outcome = 'OFFEN'"
        ).fetchall()

    for t in offene:
        high, low = _preis_seit(t['ticker'], t['gespeichert'])
        if high is None:
            continue

        outcome    = None
        exit_preis = None

        if t['richtung'] == 'LONG':
            if low <= t['stop_loss']:
                outcome    = 'LOSS'
                exit_preis = t['stop_loss']
            elif high >= t['take_profit']:
                outcome    = 'WIN'
                exit_preis = t['take_profit']
        else:  # SHORT
            if high >= t['stop_loss']:
                outcome    = 'LOSS'
                exit_preis = t['stop_loss']
            elif low <= t['take_profit']:
                outcome    = 'WIN'
                exit_preis = t['take_profit']

        if outcome:
            if t['richtung'] == 'LONG':
                pnl = (exit_preis - t['einstieg']) / t['einstieg'] * 100
            else:
                pnl = (t['einstieg'] - exit_preis) / t['einstieg'] * 100

            exit_zeit = datetime.now().strftime('%d.%m.%Y %H:%M')
            with _conn() as c:
                c.execute('''
                    UPDATE trades
                    SET outcome=?, exit_preis=?, exit_zeit=?, pnl_pct=?
                    WHERE id=?
                ''', (outcome, round(exit_preis, 4), exit_zeit,
                      round(pnl, 3), t['id']))
            updated += 1

    return updated

# ── Trade manuell schließen ───────────────────────────────────────────────────

def schliesse_trade(trade_id: int, outcome: str, exit_preis: float = None, notiz: str = ''):
    init_db()
    exit_zeit = datetime.now().strftime('%d.%m.%Y %H:%M')
    with _conn() as c:
        t = c.execute('SELECT * FROM trades WHERE id=?', (trade_id,)).fetchone()
        if not t:
            return False
        if exit_preis is None:
            exit_preis = t['einstieg']
        if t['richtung'] == 'LONG':
            pnl = (exit_preis - t['einstieg']) / t['einstieg'] * 100
        else:
            pnl = (t['einstieg'] - exit_preis) / t['einstieg'] * 100
        c.execute('''
            UPDATE trades
            SET outcome=?, exit_preis=?, exit_zeit=?, pnl_pct=?, notiz=?
            WHERE id=?
        ''', (outcome, round(exit_preis, 4), exit_zeit,
              round(pnl, 3), notiz, trade_id))
    return True

# ── Trade löschen ─────────────────────────────────────────────────────────────

def loesche_trade(trade_id: int):
    init_db()
    with _conn() as c:
        c.execute('DELETE FROM trades WHERE id=?', (trade_id,))

# ── Journal laden ─────────────────────────────────────────────────────────────

def lade_journal(limit: int = 100):
    init_db()
    with _conn() as c:
        rows = c.execute('''
            SELECT * FROM trades ORDER BY id DESC LIMIT ?
        ''', (limit,)).fetchall()
    return [dict(r) for r in rows]

def lade_statistiken():
    init_db()
    with _conn() as c:
        alle = c.execute(
            "SELECT * FROM trades WHERE outcome != 'OFFEN'"
        ).fetchall()
    alle = [dict(r) for r in alle]
    if not alle:
        return {'n': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
                'gesamt_pnl': 0, 'avg_win': 0, 'avg_loss': 0,
                'profit_factor': 0}

    wins   = [t for t in alle if t['outcome'] == 'WIN']
    losses = [t for t in alle if t['outcome'] == 'LOSS']
    n      = len(alle)

    sum_w = sum(t['pnl_pct'] for t in wins   if t['pnl_pct'])
    sum_l = sum(t['pnl_pct'] for t in losses if t['pnl_pct'])
    pf    = round(sum_w / abs(sum_l), 2) if sum_l and sum_l != 0 else 0

    return {
        'n':             n,
        'wins':          len(wins),
        'losses':        len(losses),
        'win_rate':      round(len(wins) / n * 100, 1) if n else 0,
        'gesamt_pnl':    round(sum_w + sum_l, 2),
        'avg_win':       round(sum_w / len(wins),   3) if wins   else 0,
        'avg_loss':      round(sum_l / len(losses), 3) if losses else 0,
        'profit_factor': pf,
    }
