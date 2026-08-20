# Phase E — Datenmodell + Performance-Kennzahlen

**Datum:** 2026-08-20  
**Status:** Abgeschlossen — **wartet auf Freigabe für Phase F**  
**Modus:** PAPER TRADING ONLY

---

## 1. Datenbank-Backup

| Item | Pfad |
|------|------|
| Pre-migration backup | `backups/phase-e-20260820T144643Z/bot.db.backup` |

Bestehende Daten: 1 Trade, 11 Snapshots, 23 Logs — **nicht gelöscht**.

---

## 2. Migrationsschritte

1. Backup erstellt  
2. Schema geprüft (v1)  
3. Additive `ALTER TABLE` Migration (`storage_migrate.py`)  
4. Backfill nur aus bekannten Legacy-Spalten  
5. `schema_meta.version = 2` gesetzt  
6. Verifiziert: Spalten vorhanden, Legacy-Trade lesbar  

### Mapping Legacy → TradeFill

| Alt | Neu | Bemerkung |
|-----|-----|-----------|
| `price` | `execution_price` | backfilled |
| `amount_btc` | `quantity` | backfilled |
| `amount_eur` | `gross_value` | backfilled |
| `fee_eur` | `fee` | backfilled |
| `amount_eur - fee_eur` | `net_value` | ableitbar, nicht erfunden |
| — | `symbol`, `requested_price`, `slippage`, `pnl` | **NULL** (unbekannt) |

Legacy-Spalten (`price`, `amount_eur`, `amount_btc`, `fee_eur`) bleiben erhalten.

### Snapshots

Neu: `btc_price`, `portfolio_value`, `realized_pnl`, `unrealized_pnl`, `total_pnl`  
Backfill: `btc_price ← price`, `portfolio_value ← portfolio_value_eur`  
PnL-Felder bei alten Rows: **NULL**

---

## 3. Neues Schema (Trades)

```
id, timestamp, side, reason,
balance_eur_after, balance_btc_after,
symbol, requested_price, execution_price, quantity,
gross_value, fee, slippage, net_value, pnl,
price, amount_eur, amount_btc, fee_eur   -- legacy
```

---

## 4. Performance-Komponente

**Datei:** `src/bot/performance.py` → `PerformanceCalculator`

### Definitionen

| Kennzahl | Formel |
|----------|--------|
| **Gesamt-P&L** | `portfolio_value − start_capital` |
| **Gesamtrendite** | `Gesamt-P&L / start_capital` |
| **Realisiertes P&L** | Summe geschlossener Trade-PnLs / State |
| **Unrealisiertes P&L** | `(market − entry) × btc` |
| **Gewinnrate** | `Gewinntrades / abgeschlossene Trades` (None wenn 0) |
| **Average Win/Loss** | Mittel positiver / negativer Sell-PnLs |
| **Profit Factor** | `Summe Gewinne / |Summe Verluste|`; bei nur Gewinnen: `profit_factor_infinite=True`, kein Division-by-zero |
| **Max Drawdown %** | max `(peak − value) / peak × 100` |
| **Tages-P&L** | `portfolio_now − erster Snapshot ab lokalem Mitternacht` |
| **Zeitzone** | **`Europe/Berlin`** (konfigurierbar in `app.timezone`) |

### Perioden (vorbereitet)

`1D`, `1W`, `1M`, `3M`, `6M`, `1Y` — bei fehlenden Daten: `insufficient_data=True`, Werte `None`.

### Backtest

Nutzt dieselbe `PerformanceCalculator.from_backtest_trades()`.

---

## 5. Neue / geänderte Dateien

| Datei | Rolle |
|-------|-------|
| `src/bot/storage_migrate.py` | Migration v1→v2 |
| `src/bot/performance.py` | Kennzahlen |
| `src/bot/storage.py` | TradeRecord + Snapshots erweitert |
| `src/bot/execution/paper.py` | Persistiert volle TradeFill-Felder |
| `src/bot/engine.py` | Snapshot-PnL, `get_performance()`, Backtest-Metriken |
| `src/bot/config.py` / `config.yaml` | `timezone: Europe/Berlin` |
| `run_backtest.py` | Erweiterte Kennzahlen-Ausgabe |
| `tests/test_persistence.py` | Migration + Persistenz |
| `tests/test_performance.py` | Kennzahlen + Randfälle |

---

## 6. Tests

```
python3 -m pytest -v
→ 81 passed
```

(62 Phase D + 19 neue Persistence/Performance-Tests)

---

## 7. Smoke Tests

| Test | Ergebnis |
|------|----------|
| `python3 run_bot.py --once` | ✅ |
| `python3 run_backtest.py` | ✅ (Win Rate, PF, Fees, Best/Worst) |
| Dashboard-Import | ✅ |
| Schema version | **2** |
| Bestehender Trade | lesbar, neue Felder gemappt/NULL |

---

## 8. Hinweise

- **Gesamt-P&L** = Portfolio − Startkapital (Abschnitt 7).  
  `realized + unrealized` kann durch Gebühren/Cash-Accounting abweichen und wird separat ausgewiesen.
- Kein Dashboard-Redesign (Phase F).
- Kein Live-Trading-Code.

---

## STOPP

Phase F/G **nicht** begonnen. Warte auf Architekten-Freigabe.
