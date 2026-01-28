import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time

st.set_page_config(layout="wide", page_title="Opening Auction Acceptance")

# -------------------------------
# DEMO DATA LOADER
# -------------------------------
@st.cache_data
def load_data(symbol):
    df = yf.download(
        symbol,
        interval="5m",
        period="5d",
        auto_adjust=False,
        progress=False
    )

    if df.empty:
        return pd.DataFrame()

    # Reset index if time is index
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()

    # Flatten MultiIndex columns (THIS IS THE KEY FIX)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    # Normalize time column
    if "Datetime" in df.columns:
        df.rename(columns={"Datetime": "time"}, inplace=True)
    elif "Date" in df.columns:
        df.rename(columns={"Date": "time"}, inplace=True)
    elif "time" not in df.columns:
        return pd.DataFrame()

    df["time"] = pd.to_datetime(df["time"])

    # Final safety filter
    required_cols = {"Open", "High", "Low", "Close"}
    if not required_cols.issubset(df.columns):
        return pd.DataFrame()

    return df


# -------------------------------
# UTILS
# -------------------------------
def opening_range(df):
    or_df = df[df["time"].dt.time <= time(9,35)]
    if or_df.empty:
        return None, None
    return or_df["High"].max(), or_df["Low"].min()

def premarket_levels(df):
    pm = df[df["time"].dt.time < time(9,30)]
    if pm.empty:
        return None, None
    return pm["High"].max(), pm["Low"].min()

def prior_day_levels(df):
    df["date"] = df["time"].dt.date
    dates = sorted(df["date"].unique())
    if len(dates) < 2:
        return None, None, None
    prior = df[df["date"] == dates[-2]]
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
day_type = "Rotational"

if OH is not None and OL is not None:
    if latest["Close"] > OH or latest["Close"] < OL:
        day_type = "Initiative"

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

if st.button("Export Journal"):
    journal.to_csv("oaa_journal.csv", index=False)
    st.success("Exported oaa_journal.csv")
