# Phase A — Analyse & Backup (Architekt-Freigabe)

**Datum:** 2026-08-20  
**Status:** Abgeschlossen — **wartet auf Freigabe für Phase B**  
**Modus:** PAPER TRADING ONLY (unverändert)

---

## 1. Repository-Analyse

### Projektstruktur (Ist-Zustand)

```
crypto-trading-bot/
├── README.md
├── STATUS_FUER_CHATGPT.md
├── config.yaml
├── requirements.txt
├── run_bot.py              # Paper-Trading-Loop (CLI)
├── run_backtest.py         # Backtest (CLI)
├── run_dashboard.py        # Streamlit starten
├── dashboard/app.py        # Web-Dashboard
├── data/bot.db             # SQLite (gitignored)
├── backups/phase-a-20260820/  # Phase-A-Backup (neu, lokal)
└── src/bot/
    ├── config.py           # YAML-Konfiguration
    ├── market_data.py      # Coinbase Exchange Public API
    ├── strategy.py         # EMA/RSI (noch alte Logik)
    ├── paper_trader.py     # Paper-Execution + SL/TP
    ├── storage.py          # SQLite-Persistenz
    └── engine.py           # Orchestrator + Backtester
```

### Module & Verantwortlichkeiten

| Modul | Aufgabe |
|-------|---------|
| `config.py` | Lädt `config.yaml` in `BotConfig` |
| `market_data.py` | Holt Kerzen + Spot-Preis von Coinbase Exchange (öffentlich, kein API-Key) |
| `strategy.py` | `TrendRsiStrategy` — **weicht vom Master Prompt ab** (Crossover + RSI 35/70) |
| `paper_trader.py` | Simuliert Buy/Sell inkl. Fee + Slippage, prüft SL/TP |
| `storage.py` | SQLite: `bot_state`, `trades`, `logs`, `snapshots` |
| `engine.py` | Verbindet alle Module; `TradingEngine.tick()` + `Backtester.run()` |
| `dashboard/app.py` | Streamlit UI (5 Bereiche, Logs in Aktivität gemischt) |

### Konfiguration (`config.yaml`)

| Parameter | Aktueller Wert | Soll (Architekt) |
|-----------|----------------|------------------|
| `start_capital_eur` | 50.0 | 50.0 ✅ |
| `max_trade_eur` | 10.0 | 10.0 ✅ |
| `stop_loss_pct` | 1.5 | 1.5 ✅ |
| `take_profit_pct` | 3.0 | 3.0 ✅ |
| `fee_pct` | 0.6 | 0.6 ✅ |
| `slippage_pct` | **0.05** | **0.10** ❌ (Phase C/D) |
| `product_id` | BTC-EUR | BTC-EUR ✅ |

### Abhängigkeiten

```
requests, pandas, numpy, streamlit, pyyaml
```

**pytest ist nicht installiert** — es existiert noch keine Test-Suite.

### Sicherheitsprüfung

| Prüfpunkt | Ergebnis |
|-----------|----------|
| Echtgeld-Orders | ❌ nicht vorhanden |
| Coinbase API-Keys | ❌ nicht vorhanden |
| Transfer/Auszahlung | ❌ nicht vorhanden |
| Live-Execution-Code | ❌ nicht vorhanden |
| `TRADING_MODE`-Flag | ❌ fehlt (geplant Phase B) |
| Secrets in Git | ❌ keine |

---

## 2. SQLite-Datenbank-Analyse

**Pfad:** `data/bot.db`  
**Größe:** 24 KB  
**Erstellt durch:** ersten Smoke-Test am 2026-08-20

### Tabellen & Schema

#### `bot_state` (1 Zeile)

```sql
CREATE TABLE bot_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash_eur REAL NOT NULL,
    btc_amount REAL NOT NULL,
    entry_price REAL,
    in_position INTEGER NOT NULL,
    is_running INTEGER NOT NULL,
    last_price REAL,
    last_signal TEXT NOT NULL,
    last_update TEXT,
    total_trades INTEGER NOT NULL,
    realized_pnl_eur REAL NOT NULL
);
```

**Aktuelle Daten:** 50.00 EUR Cash, 0 BTC, nicht in Position, `is_running=1`, letzter Preis 59.717,98 EUR.

#### `trades` (0 Zeilen)

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    amount_eur REAL NOT NULL,
    amount_btc REAL NOT NULL,
    fee_eur REAL NOT NULL,
    reason TEXT NOT NULL,
    balance_eur_after REAL NOT NULL,
    balance_btc_after REAL NOT NULL
);
```

**Abweichung vom Ziel-Schema:** fehlen `symbol`, `quantity` (alias amount_btc), `gross_value`, `slippage`, `net_value`, `pnl`.

#### `logs` (2 Zeilen)

- „Paper-Trading-Bot initialisiert“
- „Bot gestartet“

#### `snapshots` (1 Zeile → nach Phase-A-Smoke-Test: 2 Zeilen)

Portfolio-Snapshots für Chart-Darstellung.

### Migrations-Einschätzung

| Aspekt | Bewertung |
|--------|-----------|
| Bestehende Trades | **0** — kein Trade-Datenverlust-Risiko aktuell |
| `bot_state` | 1 Zeile — Migration mit `ALTER TABLE` oder Copy möglich |
| `trades`-Erweiterung | Neue Spalten via `ALTER TABLE ADD COLUMN` migrationsfreundlich |
| Risiko | **Niedrig** — kaum produktive Daten, aber Backup wurde trotzdem erstellt |

---

## 3. Backup

| Datei | Backup-Pfad |
|-------|-------------|
| SQLite DB | `backups/phase-a-20260820/bot.db.backup` |
| config.yaml | `backups/phase-a-20260820/config.yaml.backup` |

**Hinweis:** Backups liegen lokal (`.db` ist gitignored). Vor jedem Schema-Umbau wird erneut ein timestamped Backup erstellt.

---

## 4. Tests & Smoke Tests

### Automatisierte Tests (pytest)

| Status | Details |
|--------|---------|
| ❌ Nicht vorhanden | Kein `tests/`-Verzeichnis, pytest nicht in `requirements.txt` |

### Smoke Tests (manuell ausgeführt, Phase A)

| Test | Befehl | Ergebnis |
|------|--------|----------|
| Bot ein Tick | `python3 run_bot.py --once` | ✅ Exit 0 — Preis ~59.615 EUR, Portfolio 50 EUR |
| Backtest | `python3 run_backtest.py` | ✅ Exit 0 — 1 Trade, Rendite -0,05 % |
| Modul-Import | Python import aller `bot.*` Module | ✅ Exit 0 |

### Smoke Test nach Phase-A-Lauf (DB-Zustand)

- `bot_state`: aktualisiert (neuer Tick, neuer Snapshot)
- `trades`: weiterhin 0 (kein Kaufsignal)
- `logs`: +1 Snapshot-Eintrag
- `snapshots`: 2 Zeilen

---

## 5. Bekannte Abweichungen (für spätere Phasen)

1. **Strategie** — falsche Entry/Exit-Regeln (Phase C)
2. **Slippage** — 0,05 % statt 0,10 % (Phase C/D)
3. **Architektur** — keine Provider-Interfaces (Phase B)
4. **Trade-Schema** — unvollständig (Phase E)
5. **Kennzahlen** — unvollständig (Phase E/F)
6. **Dashboard** — Logs/Einstellungen fehlen als eigene Bereiche (Phase F)
7. **Tests** — fehlen komplett (Phase H)
8. **`TRADING_MODE=paper`** — fehlt (Phase B)

---

## 6. Geplanter nächster Schritt (Phase B — nach Freigabe)

**Was geändert wird:** Provider-Interfaces einführen, Zielstruktur anlegen, `TRADING_MODE=paper` Hard-Fail.

**Betroffene Dateien (neu/umbenannt):**

```
bot/data/base.py              (neu — MarketDataProvider)
bot/data/coinbase_public.py   (neu — aus market_data.py)
bot/execution/base.py         (neu — ExecutionProvider)
bot/execution/paper.py        (neu — aus paper_trader.py)
bot/app.py                    (neu — Orchestrator, aus engine.py extrahiert)
.env.example                  (neu — TRADING_MODE=paper)
```

**Bestehende Dateien:** bleiben vorerst als Kompatibilitäts-Wrapper, bis alle Imports umgestellt sind.

**Risiken:**

- Import-Pfade in `run_*.py` und `dashboard/app.py` müssen angepasst werden
- Kein DB-Schema-Change in Phase B geplant → **kein Datenverlustrisiko**

**Nicht in Phase B:** Strategie-Änderung, Schema-Migration, Live-Execution.

---

## 7. STOP-Regel-Check (Phase A)

| Risiko | Phase A Aktion |
|--------|----------------|
| Paper-Trades löschen | ❌ nicht betroffen — kein Refactor |
| Datenverlust | ❌ nicht betroffen — nur Backup erstellt |
| Echtgeld-Trading | ❌ nicht eingeführt |
| Sicherheit schwächen | ❌ nicht betroffen |

**Phase A abgeschlossen ohne STOP-Regel-Auslösung.**

---

## 8. Wartet auf Freigabe

Cursor wartet auf **Freigabe für Phase B** (Provider-Interfaces + `TRADING_MODE=paper`).

Kein weiterer Code-Umbau bis zur Bestätigung durch Architekt/User.
