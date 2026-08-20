# Phase B — Provider-Interfaces & PAPER-ONLY Hard Fail

**Datum:** 2026-08-20  
**Status:** Abgeschlossen — **wartet auf Freigabe für Phase C**  
**Modus:** PAPER TRADING ONLY (technisch erzwungen)

---

## Ziel (erreicht)

- Provider-Interfaces für Marktdaten und Execution eingeführt
- `TRADING_MODE=paper` als Hard-Fail beim Start
- Bestehende Entry-Points funktionsfähig
- Keine SQLite-Schema-Änderung
- pytest-Suite hinzugefügt (22 Tests, alle grün)

---

## Neue Dateien

| Datei | Zweck |
|-------|-------|
| `src/bot/data/base.py` | `MarketDataProvider` Interface |
| `src/bot/data/coinbase_public.py` | Öffentliche Coinbase-Marktdaten |
| `src/bot/data/__init__.py` | Package-Export |
| `src/bot/execution/base.py` | `ExecutionProvider` Interface |
| `src/bot/execution/paper.py` | `PaperExecutionProvider` |
| `src/bot/execution/__init__.py` | Package-Export |
| `src/bot/security.py` | `TRADING_MODE=paper` Hard-Fail |
| `src/bot/bootstrap.py` | Factory für Provider |
| `.env.example` | `TRADING_MODE=paper` |
| `pytest.ini` | Test-Konfiguration |
| `tests/conftest.py` | Fixtures |
| `tests/test_interfaces.py` | Interface-Tests |
| `tests/test_paper_execution.py` | Paper-Execution-Tests |
| `tests/test_trading_mode.py` | Sicherheits-Tests |
| `tests/test_smoke.py` | Smoke/E2E-Tests |

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `src/bot/config.py` | Getrennte Config-Sections (`app`, `trading`, `risk`, `execution`, `strategy`, `market_data`) |
| `config.yaml` | Neue Sections, `app.trading_mode: paper` |
| `src/bot/engine.py` | Nutzt Provider via Interfaces + Bootstrap |
| `src/bot/market_data.py` | Kompatibilitäts-Wrapper → `CoinbasePublicMarketData` |
| `src/bot/paper_trader.py` | Kompatibilitäts-Wrapper → `PaperExecutionProvider` |
| `run_bot.py` | `enforce_paper_trading_startup()` |
| `run_backtest.py` | `enforce_paper_trading_startup()` |
| `dashboard/app.py` | `enforce_paper_trading_startup()` beim Import |
| `requirements.txt` | `pytest>=8.0.0` |

---

## Architektur (nach Phase B)

```
TradingEngine
    ├── MarketDataProvider  →  CoinbasePublicMarketData
    └── ExecutionProvider   →  PaperExecutionProvider
```

Kein Live-Execution-Code vorhanden.

---

## Sicherheit

| Prüfpunkt | Ergebnis |
|-----------|----------|
| `TRADING_MODE=paper` Default | ✅ |
| Start bei `TRADING_MODE=live` | ❌ Hard-Fail mit `SICHERHEITSSTOPP` |
| Coinbase Trading API | ❌ nicht implementiert |
| Live Orders / Transfers | ❌ nicht implementiert |
| SQLite geändert | ❌ Schema unverändert |

Automatisierter Sicherheitstest: `test_run_bot_rejects_live_mode_smoke`, `test_trading_engine_rejects_non_paper_mode`

---

## Tests

```
python3 -m pytest -v
→ 22 passed in ~5s
```

| Kategorie | Tests |
|-----------|-------|
| Interfaces | 4 |
| Paper Execution | 6 |
| Trading Mode / Security | 8 |
| Smoke | 4 |

---

## Smoke Tests (manuell)

| Test | Ergebnis |
|------|----------|
| `python3 run_bot.py --once` | ✅ Exit 0 |
| `python3 run_backtest.py` | ✅ Exit 0 |
| Dashboard-Import | ✅ (pytest) |
| `TRADING_MODE=live run_bot.py` | ❌ startet nicht (gewollt) |

---

## SQLite

- **Keine Migration**
- **Keine Löschung**
- Schema identisch zu Phase A
- Bestehende Daten erhalten

---

## Bewusst NICHT in Phase B

- Strategie-Korrektur (Phase C)
- Slippage auf 0,10 % (Phase C/D)
- Trade-Schema-Erweiterung (Phase E)
- Dashboard-Erweiterung (Phase F)
- Backtest-Metriken (Phase G)

---

## Wartet auf Freigabe

Phase C: Strategie exakt auf Master-Prompt-Regeln umstellen.

**STOPP — kein Phase-C-Code bis zur Architekten-Freigabe.**
