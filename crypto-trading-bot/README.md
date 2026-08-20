# Crypto Paper-Trading Bot

Ein **Paper-Trading-Bot** für BTC/EUR mit Coinbase-Marktdaten, ohne echte Orders und ohne API-Key.

## Was der Bot macht

- Virtuelles Startkapital: **50 €**
- Handelt nur **BTC/EUR** (Spot, kein Hebel)
- Maximal **10 € pro Trade**
- Strategie: **EMA20/EMA50 + RSI**
- Stop-Loss: **1,5 %**, Take-Profit: **3 %**
- Simulierte Coinbase-Gebühren (**0,6 %**) und Slippage
- **Live Paper-Trading** und **Backtesting**
- Responsives **Dashboard** für Mac, PC, iPhone und iPad

**Wichtig:** Es werden **keine echten Orders** an Coinbase gesendet.

## Voraussetzungen

- Python 3.10+
- Internetverbindung für Marktdaten

## Installation

```bash
cd crypto-trading-bot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Schnellstart

### Dashboard starten (empfohlen für den ersten Test)

```bash
python run_dashboard.py
```

Öffne im Browser: `http://localhost:8501`

**iPhone/iPad im gleichen WLAN:** `http://<IP-deines-Mac/PC>:8501`

### Bot im Terminal starten

```bash
python run_bot.py
```

Nur ein Tick:

```bash
python run_bot.py --once
```

### Backtest

```bash
python run_backtest.py
```

Oder über das Dashboard unter **Backtest**.

## Dashboard-Bereiche

| Bereich | Inhalt |
|---------|--------|
| Übersicht | Portfolio, Gewinn/Verlust, Status |
| Portfolio | Portfolio-Verlauf |
| Markt | BTC-Chart mit EMA20/EMA50 und RSI |
| Aktivität | Trades und Logs |
| Backtest | Historischer Strategietest |

## Konfiguration

Alle Einstellungen in `config.yaml`:

```yaml
trading:
  start_capital_eur: 50.0
  max_trade_eur: 10.0
  stop_loss_pct: 1.5
  take_profit_pct: 3.0
```

## Nächste Schritte (später)

1. Mehrere Stunden/Tage Paper-Trading laufen lassen
2. Backtest-Ergebnisse prüfen
3. Optional: Bot auf Synology DS723+ (Ubuntu VM) umziehen
4. Optional: Tailscale für sicheren Fernzugriff
5. Erst nach guten Paper-Ergebnissen: Coinbase API (nur Trade-Rechte, keine Auszahlungen)

## Sicherheit

- Kein API-Key nötig für Paper-Trading
- Kein Hebel, kein Margin, keine Futures
- Maximaler Verlust im Paper-Modus: virtuelle 50 €

## Projektstruktur

```
crypto-trading-bot/
├── config.yaml
├── requirements.txt
├── run_bot.py
├── run_backtest.py
├── run_dashboard.py
├── dashboard/
│   └── app.py
└── src/bot/
    ├── config.py
    ├── market_data.py
    ├── strategy.py
    ├── paper_trader.py
    ├── storage.py
    └── engine.py
```
