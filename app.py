import streamlit as st
import pandas as pd
import json

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(page_title="Secure Trading Replay", layout="wide")
st.title("🔐 Secure Trading Replay & Journal")

# -------------------------------------------------
# PASSWORD GATE
# -------------------------------------------------
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.subheader("🔒 Enter Password")

    password = st.text_input("Password", type="password")

    if st.button("Unlock App"):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.success("Access granted")
            st.rerun()
        else:
            st.error("Incorrect password")

    st.stop()

check_password()

# -------------------------------------------------
# SESSION STATE INIT
# -------------------------------------------------
if "df" not in st.session_state:
    st.session_state.df = None
if "index" not in st.session_state:
    st.session_state.index = 0
if "position" not in st.session_state:
    st.session_state.position = None
if "trades" not in st.session_state:
    st.session_state.trades = []

# -------------------------------------------------
# DATA LOADER (DEMO MODE)
# -------------------------------------------------
st.subheader("📡 Market Data")

use_demo = st.checkbox("Use Demo Data", value=True)

if use_demo:
    dates = pd.date_range("2024-01-01 09:30", periods=300, freq="min")
    demo_df = pd.DataFrame({
        "Date": dates,
        "Open": 100 + pd.Series(range(300)) * 0.05,
        "High": 100 + pd.Series(range(300)) * 0.05 + 0.3,
        "Low": 100 + pd.Series(range(300)) * 0.05 - 0.3,
        "Close": 100 + pd.Series(range(300)) * 0.05 + 0.1,
        "Volume": 1000
    })

    st.session_state.df = demo_df
    st.success("Demo data loaded")

# -------------------------------------------------
# REPLAY ENGINE
# -------------------------------------------------
if st.session_state.df is not None:
    df = st.session_state.df
    idx = st.session_state.index
    row = df.iloc[idx]

    st.divider()
    st.subheader(f"🕯 Candle {idx + 1} / {len(df)}")

    st.write({
        "Date": row.Date,
        "Open": round(row.Open, 2),
        "High": round(row.High, 2),
        "Low": round(row.Low, 2),
        "Close": round(row.Close, 2),
    })

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("⏭ Next"):
            if idx < len(df) - 1:
                st.session_state.index += 1

    with col2:
        if st.button("🟢 Buy"):
            if st.session_state.position is None:
                st.session_state.position = {
                    "entry_date": str(row.Date),
                    "entry_price": row.Close,
                    "note": ""
                }

    with col3:
        if st.button("🔴 Close"):
            if st.session_state.position:
                trade = st.session_state.position
                trade["exit_date"] = str(row.Date)
                trade["exit_price"] = row.Close
                trade["pnl"] = round(row.Close - trade["entry_price"], 2)
                st.session_state.trades.append(trade)
                st.session_state.position = None

    with col4:
        if st.button("⏮ Reset"):
            st.session_state.index = 0
            st.session_state.position = None
            st.session_state.trades = []

    if st.session_state.position:
        st.session_state.position["note"] = st.text_input(
            "📝 Trade Note",
            st.session_state.position.get("note", "")
        )

# -------------------------------------------------
# SAVE / LOAD SESSION
# -------------------------------------------------
st.divider()
st.subheader("💾 Save / Load Session")

session_data = {
    "index": st.session_state.index,
    "trades": st.session_state.trades
}

session_json = json.dumps(session_data, indent=2)

st.download_button(
    "⬇ Save Session",
    session_json,
    "replay_session.json",
    "application/json"
import numpy as np
import yfinance as yf
from datetime import datetime, time

st.set_page_config(layout="wide", page_title="Opening Auction Acceptance")

# -------------------------------
# DEMO DATA LOADER
# -------------------------------
@st.cache_data
def load_data(symbol):
    df = yf.download(symbol, interval="5m", period="5d")
    df = df.reset_index()
    df.rename(columns={"Datetime": "time"}, inplace=True)
    return df

# -------------------------------
# UTILS
# -------------------------------
def opening_range(df):
    or_df = df[df["time"].dt.time <= time(9,35)]
    return or_df["High"].max(), or_df["Low"].min()

def premarket_levels(df):
    pm = df[df["time"].dt.time < time(9,30)]
    return pm["High"].max(), pm["Low"].min()

def prior_day_levels(df):
    df["date"] = df["time"].dt.date
    prior = df[df["date"] == df["date"].iloc[-1] - pd.Timedelta(days=1)]
    return prior["High"].max(), prior["Low"].min(), prior["Open"].iloc[0]

def rr(entry, stop, target):
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return round(reward / risk, 2) if risk > 0 else 0

# -------------------------------
# UI
# -------------------------------
st.title("📊 Opening Auction Acceptance (OAA)")

symbol = st.text_input("Symbol (Stocks / FX / Crypto)", "AAPL")
df = load_data(symbol)

df["time"] = pd.to_datetime(df["time"])

OH, OL = opening_range(df)
PMH, PML = premarket_levels(df)
PDH, PDL, PDO = prior_day_levels(df)

st.subheader("Key Levels")
st.write({
    "OH": OH, "OL": OL,
    "PMH": PMH, "PML": PML,
    "PDH": PDH, "PDL": PDL,
    "PDO": PDO
})

# -------------------------------
# DAY TYPE
# -------------------------------
latest = df.iloc[-1]
day_type = "Initiative" if latest["Close"] > OH or latest["Close"] < OL else "Rotational"
manual_day = st.selectbox("Day Type Override", ["Auto", "Initiative", "Rotational"])
if manual_day != "Auto":
    day_type = manual_day

st.success(f"Day Type: {day_type}")

# -------------------------------
# SIGNAL LOGIC
# -------------------------------
signals = []

for i in range(5, len(df)):
    candle = df.iloc[i]
    prev = df.iloc[i-1]

    # Initiative Break
    if candle["Close"] > OH and candle["Close"] > prev["High"]:
        entry = candle["Close"]
        stop = OL
        target = PDH
        signals.append({
            "Type": "OAA-I",
            "Entry": entry,
            "Stop": stop,
            "Target": target,
            "RR": rr(entry, stop, target)
        })

    # Rotational Acceptance
    if candle["High"] > OH and candle["Close"] < OH:
        entry = candle["Close"]
        stop = candle["High"]
        target = PDO
        signals.append({
            "Type": "OAA-R",
            "Entry": entry,
            "Stop": stop,
            "Target": target,
            "RR": rr(entry, stop, target)
        })

signals_df = pd.DataFrame(signals)

st.subheader("Trade Suggestions")
if signals_df.empty:
    st.info("No valid setups detected.")
else:
    st.dataframe(signals_df)

# -------------------------------
# JOURNAL
# -------------------------------
st.subheader("Trade Journal")
journal = st.data_editor(
    signals_df.assign(Notes=""),
    use_container_width=True,
    num_rows="dynamic"
)

uploaded_session = st.file_uploader("Load Session", type=["json"])

if uploaded_session:
    loaded = json.load(uploaded_session)
    st.session_state.index = loaded.get("index", 0)
    st.session_state.trades = loaded.get("trades", [])
    st.success("Session loaded")
    st.rerun()

# -------------------------------------------------
# TRADE JOURNAL
# -------------------------------------------------
st.divider()
st.subheader("📒 Trade Journal")

if st.session_state.trades:
    trades_df = pd.DataFrame(st.session_state.trades)
    st.dataframe(trades_df, use_container_width=True)

    csv = trades_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇ Export Trades CSV",
        csv,
        "trade_journal.csv",
        "text/csv"
    )
else:
    st.info("No trades yet.")
if st.button("Export Journal"):
    journal.to_csv("oaa_journal.csv", index=False)
    st.success("Exported oaa_journal.csv")
