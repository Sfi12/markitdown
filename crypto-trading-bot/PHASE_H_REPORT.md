# Phase H Report — Qualitätssicherung + Langzeit-Paper-Trading

**Status:** IMPLEMENTIERT — wartet auf Architektenfreigabe  
**Modus:** PAPER TRADING ONLY  
**Strategieparameter:** unverändert (EMA20/50, RSI14, Entry50/Exit45, SL1.5%, TP3%, Fee0.6%, Slip0.10%)

## Wichtige Einordnung (Backtest)

Phase-G-Zahlen (−2.04 % vs. B&H +6.47 %, 13 Trades) sind **keine** Beweisgrundlage für/gegen die Strategie. Stichprobe zu klein. In Phase H **keine** Parameteränderung.

## Neue Änderungen

| Bereich | Umsetzung |
|---------|-----------|
| Idempotenz | `last_processed_candle` in `bot_state` (Schema v3) — Strategie-Trade pro Kerze nur einmal |
| Restart | Cash/BTC/Entry/Position/Trades/PnL/Snapshots/Logs/last_processed_candle bleiben in SQLite |
| API-Resilienz | `ResilientMarketData` — Retries bei Timeout/Netzwerk/leerer/kaputter Antwort; **kein** Erfinden von Kerzen |
| Fehlerisolation | API-Fehler erhöhen Counter/`last_error`, Portfolio bleibt unverändert |
| Health | `RUNNING` / `STOPPED` / `STALE` / `ERROR` + Emojis; `stale_after_seconds` (Default 180) |
| Logging | Levels normalisiert auf `info` / `warning` / `error` |
| Report | `PaperTradingReport` (Start, Runtime, Ticks, API-Fehler, Trades, PnL, Fees, Drawdown, …) |
| Dashboard | Status-Pills + Last successful tick / Runtime / Trade count / Portfolio value |
| Config | `bot.stale_after_seconds`, `market_data_retries`, `market_data_retry_delay_seconds` |

**Nicht gemacht:** Synology-Migration, Live-Coinbase, Strategieoptimierung, Service-Manager.

## Stabilitätstests (automatisiert)

- doppelte Candle / Idempotenz (execute_signal wird nicht zweimal für dieselbe Kerze aufgerufen)
- Neustart mit persistiertem Portfolio + `last_processed_candle`
- API-Timeout / leere Antwort / Retry
- Portfolio unverändert bei API-Fehler
- STALE / ERROR / RUNNING / STOPPED
- Paper-only Hard Fail
- wiederholte Ticks, SQLite-Konsistenz, Log-Level-Normalisierung

## Manuelle Smoke-Läufe (Cloud-Agent)

| Check | Ergebnis |
|-------|----------|
| `python3 -m pytest -v` | **150 passed** |
| `python3 run_bot.py --once` | OK — 🟢 RUNNING, Report gedruckt |
| Dashboard-Import | OK |
| 3-Tick-Stress (Live-API, eigene Temp-DB) | 3/3 successful ticks, 0 API-Fehler |

## Paper-Trading-Laufzeit

| Stufe | Status |
|-------|--------|
| Unit/Smoke + 3-Tick-Live-Stichprobe | **bestanden** (dieser Agent) |
| **24 h lokal** | **noch ausstehend — vom Betreiber auf PC/Mac auszuführen** |
| 48 h / 7 Tage | erst nach stabilem 24h-Lauf |

Empfohlener lokaler Start:

```bash
cd crypto-trading-bot
PYTHONPATH=src python3 run_bot.py
# Dashboard parallel: PYTHONPATH=src streamlit run dashboard/app.py
```

Währenddessen: keine Strategie-/Parameteränderung, keine manuelle DB-Manipulation.

## Bekannte Hinweise

- `run_bot.py` setzt im `finally` `is_running=False` → Abschluss-Report zeigt ⚪ STOPPED (erwartet).
- SL/TP bleiben preisbasiert und sind von der Kerzen-Idempotenz ausgenommen (absichtlich).
- Cloud-Agent kann keinen echten 24h-Dauerlauf ersetzen.

## STOP

Phase H Code + Tests abgeschlossen. **Keine Synology-Migration. Keine Live-Integration. Keine Optimierung.**  
Nächster Schritt nur nach Architektenfreigabe (und lokalem 24h-Lauf).
