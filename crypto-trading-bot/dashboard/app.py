from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bot.config import BotConfig
from bot.engine import Backtester, TradingEngine

CONFIG = BotConfig.load(ROOT / "config.yaml")
ENGINE = TradingEngine(CONFIG)


def inject_styles(theme: str) -> None:
    is_dark = theme == "dark"
    bg = "#000000" if is_dark else "#f5f5f7"
    card = "#1c1c1e" if is_dark else "#ffffff"
    text = "#f5f5f7" if is_dark else "#1d1d1f"
    muted = "#98989d" if is_dark else "#6e6e73"
    accent = "#0a84ff"
    positive = "#30d158"
    negative = "#ff453a"
    border = "#2c2c2e" if is_dark else "#e5e5ea"

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}

        .stApp {{
            background: {bg};
            color: {text};
        }}

        .hero {{
            padding: 0.5rem 0 1.25rem 0;
        }}

        .hero h1 {{
            font-size: clamp(1.8rem, 4vw, 2.4rem);
            font-weight: 700;
            margin: 0;
            letter-spacing: -0.03em;
        }}

        .hero p {{
            color: {muted};
            margin: 0.35rem 0 0 0;
            font-size: 1rem;
        }}

        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 0.85rem;
            margin: 1rem 0 1.25rem 0;
        }}

        .metric-card {{
            background: {card};
            border: 1px solid {border};
            border-radius: 18px;
            padding: 1rem 1.1rem;
            box-shadow: 0 8px 24px rgba(0,0,0,{'0.25' if is_dark else '0.06'});
        }}

        .metric-label {{
            color: {muted};
            font-size: 0.82rem;
            margin-bottom: 0.35rem;
        }}

        .metric-value {{
            font-size: clamp(1.2rem, 3vw, 1.65rem);
            font-weight: 700;
            letter-spacing: -0.02em;
        }}

        .positive {{ color: {positive}; }}
        .negative {{ color: {negative}; }}
        .accent {{ color: {accent}; }}

        .status-pill {{
            display: inline-block;
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
            background: {'#132b18' if is_dark else '#e8f8ec'};
            color: {positive};
            border: 1px solid {'#1f4d2d' if is_dark else '#b7ebc6'};
        }}

        .status-pill.stopped {{
            background: {'#2b1717' if is_dark else '#fdecec'};
            color: {negative};
            border-color: {'#5a2323' if is_dark else '#f5c2c2'};
        }}

        .section-card {{
            background: {card};
            border: 1px solid {border};
            border-radius: 20px;
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
        }}

        .section-title {{
            font-size: 1.05rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
        }}

        div[data-testid="stSidebar"] {{
            background: {card};
            border-right: 1px solid {border};
        }}

        .stButton > button {{
            border-radius: 999px;
            border: 1px solid {border};
            background: {card};
            color: {text};
            font-weight: 600;
            padding: 0.55rem 1rem;
        }}

        .stButton > button:hover {{
            border-color: {accent};
            color: {accent};
        }}

        @media (max-width: 768px) {{
            .metric-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, css_class: str = "") -> str:
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value {css_class}">{value}</div>
    </div>
    """


def render_overview(state, price: float) -> None:
    portfolio = ENGINE.trader.portfolio_value(state, price)
    pnl = portfolio - CONFIG.start_capital_eur
    pnl_pct = (pnl / CONFIG.start_capital_eur) * 100 if CONFIG.start_capital_eur else 0
    pnl_class = "positive" if pnl >= 0 else "negative"
    status_class = "" if state.is_running else " stopped"
    status_text = "Läuft" if state.is_running else "Gestoppt"

    st.markdown(
        f"""
        <div class="hero">
            <h1>Paper Trading Dashboard</h1>
            <p>Virtuelles Startkapital · {CONFIG.product_id} · Keine echten Orders</p>
        </div>
        <div><span class="status-pill{status_class}">{status_text}</span></div>
        <div class="metric-grid">
            {metric_card("Portfolio", f"{portfolio:.2f} €", pnl_class)}
            {metric_card("BTC Preis", f"{price:.2f} €")}
            {metric_card("Gewinn/Verlust", f"{pnl:+.2f} € ({pnl_pct:+.2f} %)", pnl_class)}
            {metric_card("Cash", f"{state.cash_eur:.2f} €")}
            {metric_card("BTC Bestand", f"{state.btc_amount:.8f}")}
            {metric_card("Trades", f"{state.total_trades}")}
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Crypto Paper Bot",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    with st.sidebar:
        st.markdown("### Einstellungen")
        theme = st.selectbox("Design", ["light", "dark"], index=0)
        page = st.radio(
            "Navigation",
            ["Übersicht", "Portfolio", "Markt", "Aktivität", "Backtest"],
        )
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start"):
                ENGINE.set_running(True)
                ENGINE.tick()
                st.success("Bot gestartet")
        with col2:
            if st.button("Stop"):
                ENGINE.set_running(False)
                st.warning("Bot gestoppt")
        if st.button("Tick ausführen"):
            ENGINE.tick()
            st.info("Ein Trading-Tick ausgeführt")
        if st.button("Zurücksetzen"):
            ENGINE.reset()
            st.info("Bot zurückgesetzt")

    inject_styles(theme)
    state = ENGINE.storage.ensure_state(CONFIG.start_capital_eur)

    try:
        price = ENGINE.market.fetch_spot_price()
    except Exception as exc:
        st.error(f"Marktdaten nicht verfügbar: {exc}")
        price = state.last_price or 0.0

    if page == "Übersicht":
        render_overview(state, price)
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Letztes Signal</div>', unsafe_allow_html=True)
        st.write(state.last_signal or "Noch kein Signal")
        st.markdown("</div>", unsafe_allow_html=True)

    elif page == "Portfolio":
        render_overview(state, price)
        snapshots = ENGINE.storage.list_snapshots(limit=200)
        if snapshots:
            frame = pd.DataFrame(snapshots)
            frame["timestamp"] = pd.to_datetime(frame["timestamp"])
            st.line_chart(frame.set_index("timestamp")["portfolio_value_eur"])
        else:
            st.info("Noch keine Portfolio-Historie. Starte den Bot oder führe einen Tick aus.")

    elif page == "Markt":
        try:
            indicators = ENGINE.get_indicator_frame()
            chart = indicators.set_index("timestamp")[["close", "ema_fast", "ema_slow"]]
            st.line_chart(chart)
            latest = indicators.iloc[-1]
            cols = st.columns(3)
            cols[0].metric("RSI", f"{latest['rsi']:.1f}")
            cols[1].metric("EMA20", f"{latest['ema_fast']:.2f}")
            cols[2].metric("EMA50", f"{latest['ema_slow']:.2f}")
        except Exception as exc:
            st.error(f"Chart konnte nicht geladen werden: {exc}")

    elif page == "Aktivität":
        trades = ENGINE.storage.list_trades(limit=50)
        logs = ENGINE.storage.list_logs(limit=50)
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Trades</div>', unsafe_allow_html=True)
        if trades:
            st.dataframe(
                pd.DataFrame([trade.to_dict() for trade in trades]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.write("Noch keine Trades.")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Logs</div>', unsafe_allow_html=True)
        if logs:
            st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
        else:
            st.write("Noch keine Logs.")
        st.markdown("</div>", unsafe_allow_html=True)

    elif page == "Backtest":
        st.markdown(
            """
            <div class="hero">
                <h1>Backtest</h1>
                <p>Strategie gegen historische Coinbase-Kerzen testen</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Backtest starten"):
            with st.spinner("Backtest läuft..."):
                result = Backtester(CONFIG).run()
            cols = st.columns(3)
            cols[0].metric("Endkapital", f"{result.end_capital_eur:.2f} €")
            cols[1].metric("Rendite", f"{result.total_return_pct:+.2f} %")
            cols[2].metric("Max Drawdown", f"{result.max_drawdown_pct:.2f} %")
            st.write(
                f"Gewinner: {result.winning_trades} · Verlierer: {result.losing_trades} · "
                f"Trades: {result.total_trades}"
            )
            if result.trades:
                st.dataframe(pd.DataFrame(result.trades), use_container_width=True, hide_index=True)

    st.caption(
        "Paper-Trading only · Keine Coinbase-Orders · Für iPhone: http://<deine-ip>:8501 im gleichen WLAN"
    )


if __name__ == "__main__":
    main()
