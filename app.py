import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta

st.set_page_config(layout="wide", page_title="Opening Auction Acceptance + Manual Replay")

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

    last_date = dates[-1]
    last_datetime = pd.to_datetime(last_date)
    weekday = last_datetime.weekday()  # Monday=0, ..., Sunday=6

    # Determine prior trading day for weekends and Mondays
    if weekday == 0:  # Monday
        prior_date = last_datetime - timedelta(days=3)  # Friday
    elif weekday == 5:  # Saturday
        prior_date = last_datetime - timedelta(days=1)  # Friday
    elif weekday == 6:  # Sunday
        prior_date = last_datetime - timedelta(days=2)  # Friday
    else:
        prior_date = last_datetime - timedelta(days=1)  # Normal prior day

    # Adjust if prior_date not in available dates (holidays, etc)
    available_prior_dates = [d for d in dates if d < prior_date.date()]
    if available_prior_dates:
        prior_date = max(available_prior_dates)
    else:
        prior_date = dates[-2]  # fallback

    prior = df[df["date"] == prior_date]
    if prior.empty:
        return None, None, None

    return prior["High"].max(), prior["Low"].min(), prior["Open"].iloc[0]

def rr(entry, stop, target):
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return round(reward / risk, 2) if risk > 0 else 0

# -------------------------------
# PAGE HEADER
# -------------------------------
col_left, col_right = st.columns([3,1])

with col_left:
    st.title("📊 Opening Auction Acceptance + Manual Trading Replay")
    symbol = st.text_input("Symbol (Stocks / FX / Crypto)", "AAPL")
    st.caption("Hint: Try tickers like AAPL, EURUSD=X (FX), BTC-USD (Crypto), ES=F (Futures)")

with col_right:
    now = datetime.now()
    st.markdown(f"### ⏰ Current Time\n**{now.strftime('%Y-%m-%d %H:%M:%S')}**")

df = load_data(symbol)

if df.empty:
    st.error("No data returned. Check symbol or market hours.")
    st.stop()

# -------------------------------
# Calculate Key Levels
# -------------------------------
OH, OL = opening_range(df)
PMH, PML = premarket_levels(df)
PDH, PDL, PDO = prior_day_levels(df)

# -------------------------------
# Key Levels Section
# -------------------------------
with st.expander("🔑 Key Levels", expanded=True):
    if OH is None or OL is None:
        st.warning("Aftermarket hours — no opening range data available.")
        st.write({
            "PMH": PMH, "PML": PML,
            "PDH": PDH, "PDL": PDL,
            "PDO": PDO
        })
    else:
        st.write({
            "OH": OH, "OL": OL,
            "PMH": PMH, "PML": PML,
            "PDH": PDH, "PDL": PDL,
            "PDO": PDO
        })

# -------------------------------
# Day Type Section
# -------------------------------
with st.expander("📅 Day Type", expanded=True):
    latest = df.iloc[-1]
    day_type = "Rotational"

    if OH is not None and OL is not None:
        if latest["Close"] > OH or latest["Close"] < OL:
            day_type = "Initiative"

    manual_day = st.selectbox("Day Type Override", ["Auto", "Initiative", "Rotational"])
    if manual_day != "Auto":
        day_type = manual_day

    st.markdown(f"<h3 style='color: {'green' if day_type=='Initiative' else 'orange'};'>Day Type: {day_type}</h3>", unsafe_allow_html=True)

# -------------------------------
# Automated Trade Suggestions & Journal
# -------------------------------
with st.expander("🤖 Trade Suggestions & Automated Journal", expanded=True):

    signals = []

    if OH is None or OL is None:
        st.info("No opening range data available, so no trade signals generated.")
    else:
        for i in range(5, len(df)):
            candle = df.iloc[i]
            prev = df.iloc[i-1]

            # Skip if key values missing or NaN
            if any(val is None for val in [OH, OL, PDH, PDO]):
                continue
            if pd.isna(candle["Close"]) or pd.isna(prev["High"]):
                continue

            # Initiative Break (Long)
            if candle["Close"] > OH and candle["Close"] > prev["High"]:
                entry = candle["Close"]
                stop = OL
                target = PDH
                signals.append({
                    "Type": "OAA-I",
                    "Side": "Long",
                    "Entry": entry,
                    "Stop": stop,
                    "Target": target,
                    "RR": rr(entry, stop, target),
                    "DateTime": candle["time"]
                })

            # Rotational Acceptance (Short)
            if candle["High"] > OH and candle["Close"] < OH:
                entry = candle["Close"]
                stop = candle["High"]
                target = PDO
                signals.append({
                    "Type": "OAA-R",
                    "Side": "Short",
                    "Entry": entry,
                    "Stop": stop,
                    "Target": target,
                    "RR": rr(entry, stop, target),
                    "DateTime": candle["time"]
                })

    signals_df = pd.DataFrame(signals)

    if signals_df.empty:
        st.info("No valid setups detected.")
    else:
        if "automated_journal" not in st.session_state:
            st.session_state.automated_journal = signals_df.assign(Delete=False)

        journal_df = st.session_state.automated_journal

        edited_df = st.data_editor(
            journal_df,
            use_container_width=True,
            column_config={
                "Delete": st.column_config.CheckboxColumn("Delete")
            },
            num_rows="dynamic"
        )

        col1, col2, col3 = st.columns([1,1,1])

        with col1:
            if st.button("🗑️ Delete Selected Automated Entries"):
                st.session_state.show_auto_confirm = True

        with col2:
            if st.button("⬇ Export Automated Journal CSV"):
