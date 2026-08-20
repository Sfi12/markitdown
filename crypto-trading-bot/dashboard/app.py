from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from bot.config import BotConfig
from bot.engine import TradingEngine
from bot.security import enforce_paper_trading_startup
from bot.strategy import completed_candles_only
from dashboard.helpers import (
    bot_status_label,
    build_overview_cards,
    build_position_cards,
    filter_logs,
    format_eur,
    format_pct,
    humanize_reason,
    paper_mode_badge,
    settings_rows,
    trade_activity_cards,
)

CONFIG = BotConfig.load(ROOT / "config.yaml")
enforce_paper_trading_startup(CONFIG.trading_mode)
ENGINE = TradingEngine(CONFIG)

PAGES = ["Übersicht", "Portfolio", "Markt", "Aktivität", "Logs", "Einstellungen"]


def inject_styles(theme: str) -> None:
    is_dark = theme == "dark"
    bg = "#0b0b0c" if is_dark else "#f5f5f7"
    card = "#1c1c1e" if is_dark else "#ffffff"
    text = "#f5f5f7" if is_dark else "#1d1d1f"
    muted = "#98989d" if is_dark else "#6e6e73"
    accent = "#0a84ff"
    positive = "#30d158"
    negative = "#ff453a"
    border = "#2c2c2e" if is_dark else "#e5e5ea"
    paper = "#ff9f0a"

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        .stApp {{ background: {bg}; color: {text}; }}
        div[data-testid="stSidebar"] {{
            background: {card};
            border-right: 1px solid {border};
        }}
        .cockpit-header {{
            display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center;
            margin: 0.2rem 0 1rem 0;
        }}
        .cockpit-title {{
            font-size: clamp(1.6rem, 4vw, 2.1rem);
            font-weight: 700; letter-spacing: -0.03em; margin: 0;
        }}
        .cockpit-sub {{ color: {muted}; margin: 0.2rem 0 0 0; }}
        .pill {{
            display: inline-flex; align-items: center; gap: 0.35rem;
            padding: 0.35rem 0.75rem; border-radius: 999px;
            font-size: 0.78rem; font-weight: 650; border: 1px solid {border};
            background: {card};
        }}
        .pill.paper {{ color: {paper}; border-color: {paper}55; background: {paper}14; }}
        .pill.running {{ color: {positive}; border-color: {positive}55; background: {positive}14; }}
        .pill.stopped {{ color: {negative}; border-color: {negative}55; background: {negative}14; }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
            gap: 0.8rem; margin: 0.8rem 0 1.1rem 0;
        }}
        .metric-card, .section-card, .activity-card {{
            background: {card}; border: 1px solid {border}; border-radius: 18px;
            box-shadow: 0 10px 28px rgba(0,0,0,{'0.28' if is_dark else '0.05'});
        }}
        .metric-card {{ padding: 0.95rem 1rem; }}
        .metric-label {{ color: {muted}; font-size: 0.78rem; margin-bottom: 0.3rem; }}
        .metric-value {{
            font-size: clamp(1.05rem, 2.8vw, 1.45rem);
            font-weight: 700; letter-spacing: -0.02em;
        }}
        .positive {{ color: {positive}; }}
        .negative {{ color: {negative}; }}
        .section-card {{ padding: 1rem 1.1rem; margin-bottom: 0.95rem; }}
        .section-title {{ font-size: 1.02rem; font-weight: 650; margin-bottom: 0.7rem; }}
        .muted {{ color: {muted}; font-size: 0.9rem; }}
        .activity-card {{ padding: 0.9rem 1rem; margin-bottom: 0.7rem; }}
        .activity-top {{
            display: flex; justify-content: space-between; gap: 0.6rem;
            margin-bottom: 0.45rem; flex-wrap: wrap;
        }}
        .activity-kind {{ font-weight: 700; }}
        .kv {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 0.45rem 0.8rem;
            font-size: 0.9rem;
        }}
        .kv span {{ color: {muted}; display: block; font-size: 0.75rem; }}
        .stButton > button {{
            border-radius: 999px; border: 1px solid {border};
            background: {card}; color: {text}; font-weight: 600;
        }}
        @media (max-width: 768px) {{
            .metric-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
            .kv {{ grid-template-columns: 1fr; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_html(cards: list[dict[str, str]]) -> str:
    inner = "".join(
        f"""
        <div class="metric-card">
          <div class="metric-label">{card['label']}</div>
          <div class="metric-value {card.get('css', '')}">{card['value']}</div>
        </div>
        """
        for card in cards
    )
    return f'<div class="metric-grid">{inner}</div>'


@st.cache_data(ttl=30, show_spinner=False)
def cached_spot_price(_product_id: str) -> float:
    return ENGINE.market.fetch_spot_price()


@st.cache_data(ttl=60, show_spinner=False)
def cached_indicator_frame(_product_id: str, _granularity: int, _limit: int):
    return ENGINE.get_indicator_frame()


def render_header(state, theme: str) -> None:
    inject_styles(theme)
    running = bot_status_label(state.is_running)
    running_class = "running" if state.is_running else "stopped"
    st.markdown(
        f"""
        <div class="cockpit-header">
          <div>
            <h1 class="cockpit-title">Trading Cockpit</h1>
            <p class="cockpit-sub">{CONFIG.product_id} · virtuelles Kapital · keine echten Orders</p>
          </div>
        </div>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.9rem;">
          <span class="pill paper">{paper_mode_badge(CONFIG.trading_mode)}</span>
          <span class="pill {running_class}">{running}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_overview(state, price: float, market_error: str | None) -> None:
    metrics = ENGINE.get_performance(market_price=price if price else None)
    st.markdown(metric_html(build_overview_cards(metrics)), unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Bot-Status</div>', unsafe_allow_html=True)
        st.write(f"**Modus:** {paper_mode_badge(CONFIG.trading_mode)}")
        st.write(f"**Status:** {bot_status_label(state.is_running)}")
        st.write(f"**Letzter Tick:** {state.last_update or '—'}")
        st.write(f"**Letzter Datenabruf:** {state.last_update or '—'}")
        if market_error:
            st.warning(f"Marktdaten: {market_error}")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Strategie-Status</div>', unsafe_allow_html=True)
        try:
            frame = cached_indicator_frame(
                CONFIG.product_id,
                CONFIG.candle_granularity,
                CONFIG.candle_limit,
            )
            completed = completed_candles_only(frame)
            signal = ENGINE.strategy.evaluate(
                frame,
                in_position=state.in_position,
                exclude_open_candle=True,
            )
            row = completed.iloc[-1] if not completed.empty else None
            if row is not None and pd.notna(row.get("ema_fast")):
                st.write(f"**EMA20:** {float(row['ema_fast']):,.2f}")
                st.write(f"**EMA50:** {float(row['ema_slow']):,.2f}")
                st.write(f"**RSI14:** {float(row['rsi']):.1f}")
            else:
                st.info("Unzureichende historische Daten für Indikatoren.")
            st.write(f"**Signal:** {signal.action.value.upper()}")
            st.write(f"**Grund:** {humanize_reason(signal.reason)}")
            st.write(f"**Signal-Kerze:** {signal.signal_candle_timestamp or '—'}")
        except Exception:
            st.warning("Strategie-Status derzeit nicht verfügbar.")
            st.write(f"**Letztes Signal:** {humanize_reason(state.last_signal)}")
        st.markdown("</div>", unsafe_allow_html=True)

    position = build_position_cards(state, price, ENGINE.risk)
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Position</div>', unsafe_allow_html=True)
    if position is None:
        st.info("Keine offene Position.")
    else:
        st.markdown(metric_html(position), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_portfolio(state, price: float) -> None:
    metrics = ENGINE.get_performance(market_price=price if price else None)
    st.markdown(
        metric_html(
            [
                {
                    "label": "Realisiertes P&L",
                    "value": format_eur(metrics.realized_pnl, signed=True),
                    "css": "positive" if metrics.realized_pnl >= 0 else "negative",
                },
                {
                    "label": "Unrealisiertes P&L",
                    "value": format_eur(metrics.unrealized_pnl, signed=True),
                    "css": "positive" if metrics.unrealized_pnl >= 0 else "negative",
                },
                {
                    "label": "Gesamt-P&L",
                    "value": format_eur(metrics.total_pnl, signed=True),
                    "css": "positive" if metrics.total_pnl >= 0 else "negative",
                },
                {
                    "label": "Gesamtgebühren",
                    "value": format_eur(metrics.total_fees),
                    "css": "",
                },
            ]
        ),
        unsafe_allow_html=True,
    )

    snapshots = ENGINE.storage.list_snapshots(limit=300)
    if not snapshots:
        st.info("Keine Portfolio-Historie. Führe einen Tick aus oder starte den Bot.")
        return

    frame = pd.DataFrame(snapshots)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    value_col = "portfolio_value" if "portfolio_value" in frame else "portfolio_value_eur"
    price_col = "btc_price" if "btc_price" in frame else "price"
    chart = frame.set_index("timestamp")[[value_col]].rename(columns={value_col: "Portfolio"})
    if price_col in frame.columns:
        chart["BTC Price"] = frame.set_index("timestamp")[price_col]
    st.line_chart(chart)


def render_market(market_error: str | None) -> None:
    if market_error:
        st.warning(f"Keine aktuellen Marktdaten: {market_error}")
    try:
        frame = cached_indicator_frame(
            CONFIG.product_id,
            CONFIG.candle_granularity,
            CONFIG.candle_limit,
        )
        latest = frame.iloc[-1]
        cols = st.columns(4)
        cols[0].metric("Kurs", format_eur(float(latest["close"])))
        cols[1].metric("EMA20", f"{float(latest['ema_fast']):,.2f}")
        cols[2].metric("EMA50", f"{float(latest['ema_slow']):,.2f}")
        rsi_val = latest["rsi"]
        cols[3].metric("RSI14", "—" if pd.isna(rsi_val) else f"{float(rsi_val):.1f}")
        chart = frame.set_index("timestamp")[["close", "ema_fast", "ema_slow"]].rename(
            columns={"close": "BTC-EUR", "ema_fast": "EMA20", "ema_slow": "EMA50"}
        )
        st.line_chart(chart)
        st.caption("Nur die Indikatoren der Strategie: EMA20, EMA50, RSI14.")
    except Exception:
        st.error("Marktchart konnte nicht geladen werden. Details stehen in den Logs.")


def render_activity() -> None:
    trades = ENGINE.storage.list_trades(limit=50)
    logs = ENGINE.storage.list_logs(limit=30)
    cards = trade_activity_cards(trades)
    if not cards and not logs:
        st.info("Noch keine Aktivität.")
        return

    st.markdown('<div class="section-title">Trades</div>', unsafe_allow_html=True)
    if not cards:
        st.write("Keine Trades.")
    for card in cards:
        st.markdown(
            f"""
            <div class="activity-card">
              <div class="activity-top">
                <div class="activity-kind">{card['kind']}</div>
                <div class="muted">{card['timestamp']}</div>
              </div>
              <div class="kv">
                <div><span>Preis</span>{card['price']}</div>
                <div><span>Menge</span>{card['quantity']}</div>
                <div><span>Gebühr</span>{card['fee']}</div>
                <div><span>Slippage</span>{card['slippage']}</div>
                <div><span>P&L</span>{card['pnl']}</div>
                <div><span>Grund</span>{card['reason']}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-title">System-Ereignisse</div>', unsafe_allow_html=True)
    for log in logs[:15]:
        level = str(log.get("level", "info")).upper()
        if level in {"INFO", "TRADE", "WARNING", "WARN", "ERROR"}:
            st.write(f"**{level}** · {log.get('timestamp', '—')} — {log.get('message', '')}")


def render_logs() -> None:
    level = st.selectbox("Filter", ["ALL", "INFO", "WARNING", "ERROR"], index=0)
    logs = filter_logs(ENGINE.storage.list_logs(limit=200), level)
    if not logs:
        st.info("Keine Log-Einträge für diesen Filter.")
        return
    for log in logs:
        st.markdown(
            f"""
            <div class="activity-card">
              <div class="activity-top">
                <div class="activity-kind">{str(log.get('level','')).upper()}</div>
                <div class="muted">{log.get('timestamp','')}</div>
              </div>
              <div>{log.get('message','')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_settings() -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Konfiguration (nur Lesen)</div>', unsafe_allow_html=True)
    for label, value in settings_rows(CONFIG):
        st.write(f"**{label}:** {value}")
    st.caption(
        "Trading Mode kann hier nicht auf live gestellt werden. "
        "Strategieparameter sind absichtlich nicht editierbar."
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Paper-Bot steuern</div>', unsafe_allow_html=True)
    st.info(
        "Start/Stop setzt nur den Paper-Trading-Status in der Datenbank. "
        "Ein dauerhafter 24/7-Loop läuft über `python3 run_bot.py` — "
        "kein unsicherer Prozess-Manager im Dashboard."
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Start (Paper)", use_container_width=True):
            ENGINE.set_running(True)
            st.success("Paper-Bot Status: RUNNING")
    with c2:
        if st.button("Stop (Paper)", use_container_width=True):
            ENGINE.set_running(False)
            st.warning("Paper-Bot Status: STOPPED")
    with c3:
        if st.button("Tick ausführen", use_container_width=True):
            try:
                ENGINE.tick()
                st.success("Ein Paper-Tick ausgeführt.")
            except Exception:
                st.error("Tick fehlgeschlagen. Siehe Logs.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Gefährliche Aktion: Reset</div>', unsafe_allow_html=True)
    st.error("Reset löscht Paper-Trades, Logs und Snapshots in der lokalen Datenbank.")
    confirm = st.checkbox("Ich verstehe, dass Paper-Daten gelöscht werden.")
    if st.button("Paper-Daten zurücksetzen", disabled=not confirm):
        ENGINE.reset()
        st.warning("Paper-Datenbank zurückgesetzt. Vorheriges Backup empfohlen.")
    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="Trading Cockpit",
        page_icon="▣",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    with st.sidebar:
        st.markdown("### Navigation")
        theme = st.selectbox("Design", ["light", "dark"], index=0)
        page = st.radio("Bereich", PAGES, index=0)
        st.markdown("---")
        st.caption(paper_mode_badge(CONFIG.trading_mode))
        auto = st.toggle("Auto-Refresh (30s)", value=False)
        if auto:
            st.caption("Leichtes Polling aktiv.")

    state = ENGINE.storage.ensure_state(CONFIG.start_capital_eur)
    render_header(state, theme)

    market_error = None
    try:
        price = float(cached_spot_price(CONFIG.product_id))
    except Exception as exc:
        market_error = "Abruf fehlgeschlagen"
        price = float(state.last_price or 0.0)
        ENGINE.storage.add_log("warning", f"Marktdaten fehlgeschlagen: {exc}")

    if page == "Übersicht":
        render_overview(state, price, market_error)
    elif page == "Portfolio":
        render_portfolio(state, price)
    elif page == "Markt":
        render_market(market_error)
    elif page == "Aktivität":
        render_activity()
    elif page == "Logs":
        render_logs()
    elif page == "Einstellungen":
        render_settings()

    if auto:
        import time

        time.sleep(30)
        st.rerun()

    st.caption(
        "PAPER TRADING ONLY · Keine Live-Orders · iPhone: gleiches WLAN → http://<pc-ip>:8501"
    )


if __name__ == "__main__":
    main()
