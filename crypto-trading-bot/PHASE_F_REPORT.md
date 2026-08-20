# Phase F — Trading-Cockpit / Dashboard

**Datum:** 2026-08-20  
**Status:** Abgeschlossen — **wartet auf Freigabe für Phase G**  
**Modus:** PAPER TRADING ONLY

---

## Dashboard-Struktur

Sechs Bereiche:

1. **Übersicht** — Status, PAPER-Badge, Portfolio-Karten, Strategie-Status, Position  
2. **Portfolio** — Realisiert/Unrealisiert/Gesamt-P&L, Gebühren, Chart  
3. **Markt** — Kurs, EMA20/50, RSI14, Chart  
4. **Aktivität** — Trade-Karten (Preis, Menge, Fee, Slippage, P&L, Grund)  
5. **Logs** — eigener Bereich mit Filter INFO/WARNING/ERROR  
6. **Einstellungen** — nur Lesen + Paper Start/Stop/Tick + Reset mit Bestätigung  

---

## Neue / geänderte Dateien

| Datei | Rolle |
|-------|-------|
| `dashboard/app.py` | Trading-Cockpit UI |
| `dashboard/helpers.py` | Formatierung & View-Modelle (testbar) |
| `dashboard/__init__.py` | Package |
| `tests/test_dashboard.py` | Dashboard-Helfer-Tests |
| `tests/test_smoke.py` | Import-Smoke erweitert |
| `pytest.ini` | `pythonpath = . src` |

---

## Mobile Anpassungen

- 2-spaltige Metric-Grids auf schmalen Screens  
- Trade-Darstellung als **Karten** statt breiter Tabellen  
- Sidebar-Navigation für iPhone/iPad  
- Touchfreundliche Buttons  
- Hell-/Dunkelmodus  

---

## Start / Stop

**Umsetzung (bewusst eingeschränkt):**

- Start/Stop setzt nur `is_running` in der Paper-DB  
- „Tick ausführen“ läuft einen sicheren Paper-Tick  
- **Kein** Hintergrund-Prozess-Manager im Dashboard  

Dauerbetrieb: `python3 run_bot.py`  

Trading Mode kann im UI **nicht** auf live gestellt werden.

---

## Performance

Dashboard nutzt ausschließlich `ENGINE.get_performance()` → `PerformanceCalculator` (Phase E).

---

## Tests

```
python3 -m pytest -v
→ 91 passed
```

(81 bisher + 10 Dashboard-Tests)

Smoke:

- `run_bot.py --once` ✅  
- `run_backtest.py` ✅  
- Dashboard-Import ✅  

---

## Bekannte Einschränkungen

1. Kein 24/7-Loop aus dem Dashboard (bewusst)  
2. Auto-Refresh optional alle 30s (nicht aggressiv)  
3. Marktdaten-Cache 30–60s  
4. Visuelle Prüfung Desktop/Mobile lokal: `python3 run_dashboard.py`  

---

## STOPP

Phase G **nicht** begonnen. Warte auf Architekten-Freigabe.
