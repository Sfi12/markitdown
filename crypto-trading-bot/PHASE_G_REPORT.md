# Phase G Report — Backtesting + Strategie-Validierung

**Status:** IMPLEMENTIERT — wartet auf Architektenfreigabe  
**Modus:** PAPER TRADING ONLY (keine echten Orders, keine API Keys, keine Optimierung)

## Scope

Erweiterung des Backtesters zur seriösen Untersuchung der festen Master-Prompt-Strategie:

| Parameter | Wert |
|-----------|------|
| EMA | 20 / 50 |
| RSI | 14 |
| RSI Entry / Exit | 50 / 45 |
| Stop Loss / Take Profit | 1.5 % / 3.0 % |
| Fee / Slippage | 0.60 % / 0.10 % |
| Max Trade / Startkapital | 10 EUR / 50 EUR |

**Nicht implementiert (bewusst):** Grid Search, Parameter-Optimierung, genetische Suche, „best settings“.

## Neue Bausteine

| Modul | Rolle |
|-------|--------|
| `src/bot/backtest/periods.py` | Perioden `1W/1M/3M/6M/1Y`, Intervalle `1m/5m/15m/1h`, Coverage/`insufficient_data` |
| `src/bot/backtest/data_quality.py` | Duplikate, Sortierung, Gaps, unrealistische Preise — Blocking Errors stoppen den Lauf |
| `src/bot/backtest/benchmark.py` | Buy-&-Hold-Benchmark (gleiche Window, Fee+Slippage auf Einstieg) |
| `src/bot/backtest/engine.py` | `StrategyBacktester` + Equity/Drawdown/Streaks/Sample-Notes |
| `src/bot/data/coinbase_public.py` | `fetch_candles_range` (Pagination, keine erfundenen Kerzen) |
| `run_backtest.py` | CLI `--period` / `--interval` + vollständiger Report |
| `dashboard/helpers.py` | Backtest-Settings + `format_backtest_summary` (keine große UI) |

## Regeln eingehalten

- Keine Look-Ahead-Bias (nur abgeschlossene Bars bis Index `i`)
- Keine Interpolation / Auffüllung fehlender Historie
- Bei unzureichender Abdeckung: `insufficient_data=true` + Warnung
- Performance über zentralen `PerformanceCalculator`
- `< 30` Trades → „geringe Stichprobe“; `< 10` → „sehr geringe Stichprobe“
- Text: „Zu wenige Trades für belastbare Aussage.“ — keine Profitabilitäts-Claims

## Reproduzierbarer Backtest (Dokumentation)

Befehl:

```bash
PYTHONPATH=src python3 run_backtest.py --period 1M --interval 1h
```

| Feld | Wert |
|------|------|
| Datenquelle | Coinbase Public Exchange API (`api.exchange.coinbase.com`), **kein API-Key** |
| Candle-Intervall | `1h` (3600s) |
| Zeitraum | `1M` (~2026-07-21 → 2026-08-20 UTC) |
| Anzahl Kerzen | 720 (erwartet ~720) |
| Datenqualität | ok=True, 0 Warnings, 0 Errors, 0 Duplikate, Gaps≈0 |
| insufficient_data | false |
| Abgeschlossene Trades | 13 |
| Stichprobe | **geringe Stichprobe** — keine belastbare Strategieaussage |
| Strategie-Return | **−2.04 %** (Endkapital 48.98 EUR) |
| Buy-&-Hold-Return | **+6.47 %** (Benchmark, Endkapital 53.23 EUR) |
| Max Drawdown | 3.86 % |
| Total Fees (Strategie) | 1.6179 EUR |
| Slippage (Config) | 0.10 % (in Fills berücksichtigt) |
| Open Position am Ende | true (MTM im Endkapital) |
| Exposure | 37.1 % |
| Ø Haltedauer | ~18.4 h |

**Hinweis:** 13 Trades reichen nicht für eine belastbare Aussage. Der Vergleich zeigt nur, dass in diesem Fenster Buy & Hold besser abschnitt als die Strategie — keine Empfehlung.

## Regression

| Check | Ergebnis |
|-------|----------|
| `python3 -m pytest -v` | **135 passed** |
| `python3 run_bot.py --once` | OK (PAPER, HOLD) |
| `python3 run_backtest.py` | OK (Report inkl. B&H) |
| Dashboard-Import | OK |

## STOP

Phase G abgeschlossen. **Keine Phase H** gestartet. Warten auf Architektenfreigabe.
