import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta
import plotly.graph_objects as go

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(page_title="Trading Replay & OAA", layout="wide")

# -------------------------------------------------
# HEADER BAR
# -------------------------------------------------
colA, colB = st.columns([3, 1])
with colA:
    st.title("📈 Trading Replay & Opening Auction Acceptance")
with colB:
    st.markdown(f"🕒 **{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")

# -------------------------------------------------
# SYMBOL + TIMEFRAME
# -------------------------------------------------
st.markdown("### Asset Selection")

symbol = st.text_input("Symbol (Stocks / Crypto / FX)", "AAPL")

tf_map = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m"
}
timeframe = st.selectbox("Timeframe", list(tf_map.keys()), index=0)
interval = tf_map[timeframe]

st.caption("Examples: AAPL, MSFT, SPY, BTC-USD, EURUSD=X")

# -------------------------------------------------
# DATA LOADER (WITH PREMARKET)
# -------------------------------------------------
@st.cache_data
def load_data(symbol, interval):
    df = yf.download(
        symbol,
        interval=interval,
        period="7d",
        prepost=True,  # PREMARKET ENABLED
        progress=False,
        auto_adjust=False
    )

    if df.empty:
        return pd.DataFrame()

    df = df.reset_index()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    if "Datetime" in df.columns:
        df.rename(columns={"Datetime": "time"}, inplace=True)
    elif "Date" in df.columns:
        df.rename(columns={"Date": "time"}, inplace=True)

    df["time"] = pd.to_datetime(df["time"])
    df["date"] = df["time"].dt.date
    df["session"] = df["time"].dt.time

    return df


df = load_data(symbol, interval)

if df.empty:
    st.error("No data returned. Try another symbol.")
    st.stop()

# -------------------------------------------------
# LEVEL CALCULATIONS
# -------------------------------------------------
def opening_range(df):
    or_df = df[(df["session"] >= time(9,30)) & (df["session"] <= time(9,35))]
    if or_df.empty:
        return None, None
    return or_df["High"].max(), or_df["Low"].min()

def premarket_levels(df):
    pm = df[df["session"] < time(9,30)]
    if pm.empty:
        return None, None
    return pm["High"].max(), pm["Low"].min()

def prior_day_levels(df):
    dates = sorted(df["date"].unique())
    if len(dates) < 2:
        return None, None, None
    prior = df[df["date"] == dates[-2]]
    return prior["High"].max(), prior["Low"].min(), prior["Open"].iloc[0]

OH, OL = opening_range(df)
PMH, PML = premarket_levels(df)
PDH, PDL, PDO = prior_day_levels(df)

# -------------------------------------------------
# DISPLAY LEVELS
# -------------------------------------------------
st.markdown(f"## **{symbol.upper()} Key Levels**")

st.write({
    "Opening High": OH,
    "Opening Low": OL,
    "Premarket High": PMH,
    "Premarket Low": PML,
    "Prior Day High": PDH,
    "Prior Day Low": PDL,
    "Prior Day Open": PDO
})

# -------------------------------------------------
# SESSION FILTERS
# -------------------------------------------------
st.markdown("### Session Overlays")
sessions_selected = st.multiselect(
    "Highlight Sessions",
    ["Asia", "London", "New York"],
    default=["New York"]
)

session_ranges = {
    "Asia": (time(20,0), time(2,0)),
    "London": (time(3,0), time(11,0)),
    "New York": (time(9,30), time(16,0))
}

# -------------------------------------------------
# CHART
# -------------------------------------------------
st.markdown("## Price Chart")

fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=df["time"],
    open=df["Open"],
    high=df["High"],
    low=df["Low"],
    close=df["Close"],
    name="Price"
))

def add_level(price, label, color):
    if price is not None:
        fig.add_hline(y=price, line_dash="dash", annotation_text=label)

add_level(OH, "OH", "green")
add_level(OL, "OL", "red")
add_level(PMH, "PMH", "purple")
add_level(PML, "PML", "purple")
add_level(PDH, "PDH", "blue")
add_level(PDL, "PDL", "blue")

fig.update_layout(height=520, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

# -------------------------------------------------
# DAY TYPE LOGIC
# -------------------------------------------------
latest = df.iloc[-1]
day_type = "Rotational"

if OH and OL:
    if latest["Close"] > OH or latest["Close"] < OL:
        day_type = "Initiative"

manual_override = st.selectbox("Day Type Override", ["Auto", "Initiative", "Rotational"])
if manual_override != "Auto":
    day_type = manual_override

st.success(f"Day Type: {day_type}")

# -------------------------------------------------
# TRADE SIGNAL ENGINE
# -------------------------------------------------
def rr(entry, stop, target):
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return round(reward / risk, 2) if risk else 0

signals = []

for i in range(5, len(df)):
    candle = df.iloc[i]
    prev = df.iloc[i-1]

    if OH and PDH:
        if candle["Close"] > OH and candle["Close"] > prev["High"]:
            signals.append({
                "Type": "OAA-I",
                "Side": "LONG",
                "Time": candle["time"],
                "Entry": candle["Close"],
                "Stop": OL,
                "Target": PDH,
                "RR": rr(candle["Close"], OL, PDH)
            })

    if OH and PDO:
        if candle["High"] > OH and candle["Close"] < OH:
            signals.append({
                "Type": "OAA-R",
                "Side": "SHORT",
                "Time": candle["time"],
                "Entry": candle["Close"],
                "Stop": candle["High"],
                "Target": PDO,
                "RR": rr(candle["Close"], candle["High"], PDO)
            })

signals_df = pd.DataFrame(signals)

# -------------------------------------------------
# TAB SYSTEM (AUTO / MANUAL / BOTH)
# -------------------------------------------------
view_mode = st.radio("View Mode", ["Automatic Only", "Manual Only", "Both"], horizontal=True)

auto_tab, manual_tab = st.tabs(["📡 Automated", "🎮 Manual Replay"])

# -------------------------------------------------
# AUTOMATED TAB
# -------------------------------------------------
if view_mode in ["Automatic Only", "Both"]:
    with auto_tab:
        st.subheader("📡 Automated Trade Suggestions")

        if signals_df.empty:
            st.info("No valid setups detected.")
        else:
            st.dataframe(signals_df, use_container_width=True)

# -------------------------------------------------
# MANUAL REPLAY ENGINE
# -------------------------------------------------
if "index" not in st.session_state:
    st.session_state.index = 0
if "position" not in st.session_state:
    st.session_state.position = None
if "trades" not in st.session_state:
    st.session_state.trades = []

if view_mode in ["Manual Only", "Both"]:
    with manual_tab:
        st.subheader("🎮 Manual Replay")

        idx = st.slider("Replay Position", 0, len(df)-1, st.session_state.index)
        st.session_state.index = idx

        row = df.iloc[idx]

        st.write({
            "Time": row["time"],
            "Open": row["Open"],
            "High": row["High"],
            "Low": row["Low"],
            "Close": row["Close"]
        })

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("⏮ Previous"):
                st.session_state.index = max(0, st.session_state.index - 1)

        with col2:
            if st.button("⏭ Next"):
                st.session_state.index = min(len(df)-1, st.session_state.index + 1)

        with col3:
            if st.button("🟢 Buy"):
                if st.session_state.position is None:
                    st.session_state.position = {
                        "entry_time": row["time"],
                        "entry_price": row["Close"],
                        "note": ""
                    }

        with col4:
            if st.button("🔴 Sell / Close"):
                if st.session_state.position:
                    trade = st.session_state.position
                    trade["exit_time"] = row["time"]
                    trade["exit_price"] = row["Close"]
                    trade["pnl"] = round(row["Close"] - trade["entry_price"], 2)
                    st.session_state.trades.append(trade)
                    st.session_state.position = None

        if st.session_state.position:
            st.session_state.position["note"] = st.text_input(
                "📝 Trade Note",
                st.session_state.position.get("note", "")
            )

# -------------------------------------------------
# JOURNAL WITH DELETE CONFIRMATION
# -------------------------------------------------
st.divider()
st.subheader("📒 Trade Journal")

if st.session_state.trades:
    trades_df = pd.DataFrame(st.session_state.trades)

    delete_index = st.selectbox("Delete Trade", ["None"] + list(trades_df.index))

    if delete_index != "None":
        if st.button("⚠ Confirm Delete"):
            st.session_state.trades.pop(int(delete_index))
            st.success("Trade deleted")

    st.dataframe(trades_df, use_container_width=True)

    csv = trades_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Download Trades CSV", csv, "trade_journal.csv", "text/csv")

else:
    st.info("No trades recorded yet.")
