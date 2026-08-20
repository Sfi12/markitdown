# Phase C — Strategie-Korrektur

**Datum:** 2026-08-20  
**Status:** Abgeschlossen — **wartet auf Freigabe für Phase D**  
**Modus:** PAPER TRADING ONLY

---

## Strategieänderungen

### Entfernt (alte Logik)
- EMA-Crossover-Signale
- RSI Oversold/Overbought (35/70)

### Neu (Master Prompt)

| Regel | Bedingung |
|-------|-----------|
| **ENTRY** | `EMA20 > EMA50` **AND** `RSI14 > 50` (nur flat) |
| **EXIT** | `EMA20 < EMA50` **OR** `RSI14 < 45` (nur in Position) |
| **Stop-Loss** | 1,5 % (Execution/Risk-Schicht, reason: `stop_loss`) |
| **Take-Profit** | 3,0 % (Execution/Risk-Schicht, reason: `take_profit`) |

### Look-Ahead-Bias-Schutz

| Modus | Kerzen für Signal | Ausführungspreis |
|-------|-------------------|------------------|
| **Live** (`exclude_open_candle=True`) | Letzte **abgeschlossene** Kerze (offene Kerze wird verworfen) | Spot-Preis |
| **Backtest** (`exclude_open_candle=False`) | Aktuelle abgeschlossene Kerze am Bar | Close der Kerze |

Signal enthält `signal_candle_timestamp` zur Nachvollziehbarkeit.

---

## Neue Dateien

| Datei | Zweck |
|-------|-------|
| `src/bot/strategy/__init__.py` | Package-Export |
| `src/bot/strategy/indicators.py` | EMA, RSI, completed-candles-Filter |
| `src/bot/strategy/ema_rsi.py` | `EmaRsiStrategy` |
| `tests/test_strategy.py` | 18 Strategie-Tests |

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `src/bot/strategy.py` | **Entfernt** → ersetzt durch Package |
| `src/bot/config.py` | `rsi_entry` / `rsi_exit` statt oversold/overbought |
| `config.yaml` | `rsi_entry: 50`, `rsi_exit: 45`, `slippage_pct: 0.10` |
| `src/bot/engine.py` | `EmaRsiStrategy`, live/backtest candle-Modi |
| `src/bot/execution/paper.py` | Exit-reasons: `stop_loss`, `take_profit` |
| `tests/test_paper_execution.py` | SL/TP-Level + Slippage 0,10 % |

## Nicht geändert

- SQLite-Schema
- Dashboard (funktioniert weiter)
- Kein Live-Trading-Code

---

## Tests

```
python3 -m pytest -v
→ 44 passed (22 Phase B + 22 neue/erweiterte)
```

### Neue Strategie-Tests

- EMA20/EMA50 korrekt + unzureichende Daten
- RSI14 korrekt + unzureichende Daten + Grenzwerte
- BUY / HOLD / SELL Szenarien
- Position Safety (kein Doppel-Kauf/-Verkauf)
- Stop-Loss 98,50 / Take-Profit 103,00
- Slippage Default 0,10 %
- Look-Ahead-Bias-Tests
- Backtest/Live teilen dieselbe `EmaRsiStrategy`-Klasse

---

## Smoke Tests

| Test | Ergebnis |
|------|----------|
| `python3 run_bot.py --once` | ✅ |
| `python3 run_backtest.py` | ✅ (+0,33 %, 4 Trades, neue Signalgründe) |
| Dashboard-Import | ✅ |

---

## Bestätigung: Kein Look-Ahead Bias

- Live: `completed_candles_only()` entfernt die potenziell offene letzte Kerze
- Backtest: alle Kerzen im Fenster sind historisch abgeschlossen
- Indikatoren werden nur aus Vergangenheits-Closes berechnet
- Automatisierter Test: `test_no_look_ahead_signal_ignores_last_open_candle`

---

## STOPP

Phase D/E/F/G **nicht** begonnen. Warte auf Architekten-Freigabe.
