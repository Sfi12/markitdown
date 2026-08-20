# Statusbericht für ChatGPT (Architekt/Planer)

**Stand:** 2026-08-20  
**Projektpfad:** `crypto-trading-bot/`  
**Branch:** `cursor/crypto-paper-trading-bot-eb23`  
**PR:** https://github.com/Sfi12/markitdown/pull/1  
**Quelle bisher:** geteilter ChatGPT-Chat + Master Prompt (Vergleich noch nicht vollständig umgesetzt)

---

## Rollenklarheit

| Rolle | Wer | Aufgabe |
|-------|-----|---------|
| **Architekt / Planer** | ChatGPT | Strategie, Systemdesign, Risikoregeln, Prompts für Cursor, Code-Reviews, Weiterentwicklung |
| **Entwickler** | Cursor | Vorgaben umsetzen, Code schreiben, Tests ausführen, Fehler korrigieren |
| **Trader** | Bot | Zunächst **ausschließlich Paper-Trades** |
| **Cockpit** | Dashboard | Verständlich zeigen, was der Bot gerade macht |

**Regel:** ChatGPT plant und freigibt. Cursor implementiert erst nach Freigabe. Der Bot handelt kein Echtgeld. Das Dashboard steuert/beobachtet nur Paper-Trading.

---

## Kurzfassung für ChatGPT

Es existiert bereits ein **funktionierender Paper-Trading-Prototyp** unter `crypto-trading-bot/`.  
Er wurde aus dem geteilten Chat gebaut, **bevor** der Master Prompt vollständig als Architektur-Vorgabe angewendet wurde.

Ein Abgleich mit dem Master Prompt ist gemacht.  
**Refactor / Strategie-Korrektur / Tests / Dashboard-Lücken sind geplant, aber noch nicht freigegeben und noch nicht umgesetzt.**

Aktueller Modus: **PAPER TRADING ONLY** — keine Coinbase API-Keys, keine echten Orders.

---

## Was bereits existiert (Cursor hat geliefert)

### Lauffähig

- Virtuelles Startkapital: **50 EUR**
- Paar: **BTC-EUR**
- Max. Positionsgröße: **10 EUR**
- Spot-Simulation, kein Hebel / Margin / Futures / Shorts
- Öffentliche Coinbase-Marktdaten (kein API-Key)
- Gebühren-Simulation: **0,60 %**
- Slippage-Simulation: aktuell **0,05 %** (Master Prompt fordert **0,10 %**)
- Stop-Loss: **1,5 %**
- Take-Profit: **3 %**
- Persistenz: SQLite (`data/bot.db`)
- Streamlit-Dashboard (Hell/Dunkel, grundsätzlich responsive)
- CLI: `run_bot.py`, `run_backtest.py`, `run_dashboard.py`
- Smoke-Test bestanden: `run_bot.py --once` und `run_backtest.py`

### Dateistruktur (aktuell)

```
crypto-trading-bot/
├── README.md
├── config.yaml
├── requirements.txt
├── run_bot.py
├── run_backtest.py
├── run_dashboard.py
├── dashboard/app.py
└── src/bot/
    ├── config.py
    ├── market_data.py
    ├── strategy.py
    ├── paper_trader.py
    ├── storage.py
    └── engine.py
```

### Dashboard-Bereiche (aktuell)

| Bereich | Status |
|---------|--------|
| Übersicht | Teilweise (Status, Portfolio, Cash, BTC, Kurs, Trades) |
| Portfolio | Teilweise (Verlauf) |
| Markt | Teilweise (Preis + EMA20/50 + RSI) |
| Aktivität | Teilweise (Trades + Logs gemischt) |
| Logs | Nicht als eigener Bereich |
| Einstellungen | Nicht als eigener Bereich (nur Sidebar: Theme, Start/Stop/Tick/Reset) |

---

## Abweichungen vom Master Prompt (wichtig für Architektur)

### 1. Strategie — FALSCH / abweichend

**Master Prompt (Soll):**
- Einstieg: `EMA20 > EMA50` **UND** `RSI > 50`
- Ausstieg: `EMA20 < EMA50` **ODER** `RSI < 45`

**Aktuell (Ist):**
- Crossover-Logik + RSI-Oversold/Overbought (35 / 70)

→ Strategie muss bei nächster Freigabe korrigiert werden.

### 2. Architektur — zu flach

**Soll:** modular (`strategy`, `risk`, `execution`, `portfolio`, `data`) + Provider-Interfaces  
**Ist:** flache Module unter `src/bot/`, keine `MarketDataProvider` / `PaperExecutionProvider`-Abstraktion

### 3. Sicherheit — funktional ok, formal unvollständig

**Ist gut:** kein Live-Trading-Code, keine API-Keys, keine Secrets  
**Fehlt:** explizites `TRADING_MODE=paper`, Hard-Fail gegen versehentliches Live-Umschalten

### 4. Kennzahlen — unvollständig

Fehlen u. a. im Dashboard:
- Tages-P&L
- Gesamt-P&L klar getrennt
- Gewinnrate
- maximaler Drawdown (live)
- unrealisiertes vs. realisiertes P&L klar ausgewiesen

### 5. Trade-Schema — unvollständig

Fehlen bzw. unvollständig:
- slippage als eigenes Feld
- quantity klar
- pnl pro Trade durchgängig

### 6. Backtest — nur Basis

Vorhanden: Start/Endkapital, Rendite, Trade-Anzahl, Win/Loss, Max Drawdown  
Fehlen: Profit Factor, avg win/loss, fees total, beste/schlechteste Trades, Zeiträume 1W–1J

### 7. Tests — fehlen komplett

Kein `tests/`-Verzeichnis, keine pytest-Suite.

### 8. Prozess

Master Prompt sagte: erst Architekturanalyse, dann Freigabe, dann Code.  
Prototyp wurde trotzdem schon gebaut (aus dem Chat-Link).  
Nächster Schritt: **ChatGPT prüft/freigibt Refactor-Plan**, Cursor setzt um.

---

## Empfohlene Zielarchitektur (von Cursor vorgeschlagen, wartend auf ChatGPT-Freigabe)

```
crypto-trading-bot/
├── config/default.yaml
├── bot/
│   ├── strategy/
│   ├── risk/
│   ├── execution/      # nur Paper in Phase 1–4
│   ├── portfolio/
│   └── data/           # MarketDataProvider Interface
├── dashboard/
├── backtest/
├── tests/
└── utils/
```

**Tech-Stack (Vorschlag):**
- Python 3.10+
- Streamlit (Dashboard)
- pandas/numpy
- SQLite
- requests (öffentliche Marktdaten)
- pytest
- YAML + `TRADING_MODE=paper`

**Warum Streamlit:** schnell, Python-native, ausreichend für Desktop/iPhone im WLAN/Tailscale, kein Extra-Frontend-Build für den Prototyp.

---

## Phasen (Master Prompt) — Status

| Phase | Inhalt | Status |
|-------|--------|--------|
| 1 | Struktur, Paper Trading, Marktdaten, Strategie, Dashboard, Tests | **Prototyp da, Master-Prompt-konform noch offen** |
| 2 | Backtesting, Statistiken, Performance | teilweise begonnen |
| 3 | 24/7 Synology DS723+ Ubuntu VM | geplant, nicht gestartet |
| 4 | Tailscale/VPN | geplant, nicht gestartet |
| 5 | Optionale Coinbase-Integration | **nicht starten** |
| 6 | Vorsichtiger Echtgeldbetrieb | **nicht starten** |

---

## Offene Klärungen an ChatGPT (Architekt)

1. **Slippage-Default:** Master Prompt 0,10 % — als neuer Default übernehmen?  
2. **Bestehende SQLite-DB:** beim Refactor zurücksetzen oder migrieren?  
3. **Strategie-Korrektur:** sofort auf Master-Prompt-Regeln umstellen (EMA/RSI wie spezifiziert)?  
4. **Refactor-Freigabe:** darf Cursor die Zielstruktur + Tests + Dashboard-Lücken jetzt umsetzen?

---

## Was Cursor als Nächstes tun soll (nach Freigabe durch ChatGPT)

1. Refactor auf Zielstruktur + Provider-Interfaces  
2. Strategie exakt auf Master-Prompt-Regeln setzen  
3. Risk / Portfolio / Execution trennen  
4. Trade-Schema und Kennzahlen vervollständigen  
5. Dashboard: Übersicht / Portfolio / Markt / Aktivität / Logs / Einstellungen  
6. pytest-Suite laut Master Prompt  
7. Backtest-Metriken erweitern  
8. Weiterhin: **kein Live-Trading-Code, keine Coinbase-Keys**

---

## Harte Sicherheitsregeln (unverändert gültig)

- PAPER TRADING ONLY  
- KEINE echten Orders  
- KEINE Coinbase API Keys  
- KEIN Echtgeld  
- KEINE Auszahlung / Transfer / Einzahlung  
- Live-Trading erst ab Phase 5/6 und nur nach expliziter Multi-Gate-Freigabe  

---

## Nachricht an ChatGPT (zum Einfügen)

> Hier ist der gemeinsame Projektstand. Cursor hat einen Paper-Trading-Prototyp gebaut. Der Master Prompt ist analysiert; Abweichungen (vor allem Strategie, Architektur, Tests, Dashboard-Kennzahlen) sind dokumentiert. Bitte als Architekt: (1) Status prüfen, (2) offene Klärungen beantworten, (3) Refactor freigeben oder Plan anpassen. Cursor wartet auf deine Freigabe und implementiert danach schrittweise. Kein Echtgeld, keine echten Orders.
