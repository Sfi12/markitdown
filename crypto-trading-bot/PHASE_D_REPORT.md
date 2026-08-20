# Phase D — Risk / Portfolio / Execution

**Datum:** 2026-08-20  
**Status:** Abgeschlossen — **wartet auf Freigabe für Phase E**  
**Modus:** PAPER TRADING ONLY

---

## Ziel (erreicht)

Saubere Trennung der Verantwortlichkeiten:

| Komponente | Verantwortung |
|------------|---------------|
| **Strategy** (`EmaRsiStrategy`) | Nur Signal BUY/SELL/HOLD — **unverändert** seit Phase C |
| **Risk** (`RiskManager`) | Positionsgröße, Cash-Check, SL/TP, Order-Validierung |
| **Portfolio** (`PortfolioLedger`) | Cash/BTC/Entry, market/portfolio value, realized/unrealized/total P&L |
| **Execution** (`PaperExecutionProvider`) | Nur Paper-Simulation: Slippage + Fee → `TradeFill` |

---

## Neue Dateien

| Datei | Zweck |
|-------|-------|
| `src/bot/risk/__init__.py` | Package |
| `src/bot/risk/manager.py` | `RiskManager`, `RiskDecision` |
| `src/bot/portfolio/__init__.py` | Package |
| `src/bot/portfolio/ledger.py` | `PortfolioLedger`, `PortfolioSnapshot` |
| `tests/test_risk.py` | Risk-Tests |
| `tests/test_portfolio.py` | Portfolio-Tests |

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `src/bot/execution/base.py` | `TradeFill` + erweitertes `ExecutionResult` |
| `src/bot/execution/paper.py` | Risk → Fill → Portfolio Flow |
| `src/bot/bootstrap.py` | Factories für Risk/Portfolio |
| `src/bot/engine.py` | Engine verdrahtet Strategy/Risk/Portfolio/Execution |
| `tests/test_paper_execution.py` | Fee/Slippage/TradeFill-Tests |

## Nicht geändert

- Strategie-Regeln (EMA/RSI)
- SQLite-Schema (keine Migration)
- Dashboard UI
- Kein Live-Trading-Code

---

## Flow

```
Strategy Signal  ──┐
                   ├──▶ Risk.validate / size / SL-TP
Risk Exit (SL/TP)──┘
                         │ approved
                         ▼
                   PaperExecution (fee 0.6%, slip 0.10%)
                         │ TradeFill
                         ▼
                   PortfolioLedger.apply_*
                         │
                         ▼
                   Storage (bestehendes Schema)
```

### Slippage (exakt)

- BUY: `price * (1 + 0.001)`
- SELL: `price * (1 - 0.001)`

### Positionsgröße

- `min(10 EUR, available_cash)`

### TradeFill (Phase-E-ready)

`side, symbol, requested_price, execution_price, quantity, gross_value, fee, slippage, net_value, pnl, reason, timestamp`

Persistenz weiterhin über bestehendes SQLite-Trade-Schema (Migration = Phase E).

---

## Tests

```
python3 -m pytest -v
→ 62 passed
```

| Suite | Anzahl |
|-------|--------|
| Interfaces | 4 |
| Paper Execution | 15 |
| Portfolio | 4 |
| Risk | 9 |
| Strategy | 18 |
| Trading Mode | 8 |
| Smoke | 4 |

---

## Smoke Tests

| Test | Ergebnis |
|------|----------|
| `python3 run_bot.py --once` | ✅ |
| `python3 run_backtest.py` | ✅ (+0,50 %, 5 Trades) |
| Dashboard-/Engine-Import | ✅ Risk/Portfolio/Execution verdrahtet |

---

## Sicherheit

- PAPER ONLY
- Keine echten Orders
- Keine Coinbase API Keys
- Keine Transfers
- Ablehnungen werden geloggt (`warn`)

---

## STOPP

Phase E/F/G **nicht** begonnen. Warte auf Architekten-Freigabe.
