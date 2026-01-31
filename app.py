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
# UI - Title & Symbol Input + Current Time Display
# -------------------------------
colA, colB = st.columns([3,1])
with colA:
    st.title("📊 Opening Auction Acceptance + Manual Trading Replay")
    symbol = st.text_input("Symbol (Stocks / FX / Crypto)", "AAPL")
    st.caption("Hint: Enter ticker symbols like AAPL, EURUSD=X (FX), BTC-USD (Crypto), ES=F (Futures)")

with colB:
    # Show current date and time top right, update on rerun
    now = datetime.now()
    st.markdown(f"**Current Time:** {now.strftime('%Y-%m-%d %H:%M:%S')}")

df = load_data(symbol)

if df.empty:
    st.error("No data returned. Check symbol or market hours.")
    st.stop()

# -------------------------------
# Calculate key levels
# -------------------------------
OH, OL = opening_range(df)
PMH, PML = premarket_levels(df)
PDH, PDL, PDO = prior_day_levels(df)

# -------------------------------
# Display key levels or after hours warning
# -------------------------------
st.subheader("Key Levels")
if OH is None or OL is None:
    st.warning("Aftermarket hours - no opening range data available.")
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
# Day Type (Initiative or Rotational)
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
# Automated Signal Generation (with Side field)
# -------------------------------
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

# -------------------------------
# Automated Trade Journal with delete option
# -------------------------------
st.subheader("Trade Suggestions & Journal (Automated)")

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

    if st.button("Delete Selected Automated Entries"):
        st.session_state.show_auto_confirm = True

    if st.session_state.get("show_auto_confirm", False):
        confirm = st.checkbox("Confirm deletion of selected automated entries")
        if confirm:
            st.session_state.automated_journal = edited_df[~edited_df["Delete"].fillna(False)].reset_index(drop=True)
            st.success("Deleted selected automated entries.")
            st.session_state.show_auto_confirm = False

    if st.button("Export Automated Journal"):
        export_df = st.session_state.automated_journal.drop(columns=["Delete"], errors="ignore")
        export_df.to_csv("oaa_journal.csv", index=False)
        st.success("Exported oaa_journal.csv")

# -------------------------------
# MANUAL TRADING REPLAY with previous & next buttons
# -------------------------------
st.divider()
st.subheader("🔄 Manual Trading Replay")

# Initialize session state for replay
if 'df_replay' not in st.session_state:
    st.session_state.df_replay = df.copy()
if 'index' not in st.session_state:
    st.session_state.index = 0
if 'position' not in st.session_state:
    st.session_state.position = None
if 'trades' not in st.session_state:
    st.session_state.trades = []

df_replay = st.session_state.df_replay
idx = st.session_state.index
row = df_replay.iloc[idx]

st.write({
    "Date": row["time"],
    "Open": round(row.Open, 2),
    "High": round(row.High, 2),
    "Low": round(row.Low, 2),
    "Close": round(row.Close, 2),
})

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    if st.button("⏮ Previous Candle"):
        if st.session_state.index > 0:
            st.session_state.index -= 1

with col2:
    if st.button("⏭ Next Candle"):
        if st.session_state.index < len(df_replay) - 1:
            st.session_state.index += 1

with col3:
    if st.button("🟢 Buy"):
        if st.session_state.position is None:
            st.session_state.position = {
                "entry_date": row["time"],
                "entry_price": row.Close,
                "note": ""
            }

with col4:
    if st.button("🔴 Sell / Close"):
        if st.session_state.position is not None:
            trade = st.session_state.position
            trade["exit_date"] = row["time"]
            trade["exit_price"] = row.Close
            trade["pnl"] = round(row.Close - trade["entry_price"], 2)
            st.session_state.trades.append(trade)
            st.session_state.position = None

with col5:
    if st.button("🔄 Reset Session"):
        st.session_state.index = 0
        st.session_state.position = None
        st.session_state.trades = []

if st.session_state.position is not None:
    st.session_state.position["note"] = st.text_input(
        "📝 Trade Note",
        st.session_state.position.get("note", "")
    )

# -------------------------------
# MANUAL TRADE JOURNAL with deletion and confirmation
# -------------------------------
st.divider()
st.subheader("📒 Manual Trade Journal")

if st.session_state.trades:
    manual_trades_df = pd.DataFrame(st.session_state.trades)
    if "Delete" not in manual_trades_df.columns:
        manual_trades_df["Delete"] = False

    edited_manual_df = st.data_editor(
        manual_trades_df,
        use_container_width=True,
        column_config={
            "Delete": st.column_config.CheckboxColumn("Delete")
        },
        num_rows="dynamic"
    )

    if st.button("Delete Selected Manual Entries"):
        st.session_state.show_manual_confirm = True

    if st.session_state.get("show_manual_confirm", False):
        confirm_manual = st.checkbox("Confirm deletion of selected manual entries")
        if confirm_manual:
            st.session_state.trades = edited_manual_df[~edited_manual_df["Delete"].fillna(False)].drop(columns=["Delete"]).to_dict('records')
            st.success("Deleted selected manual entries.")
            st.session_state.show_manual_confirm = False

    csv = pd.DataFrame(st.session_state.trades).to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇ Download Manual Trades CSV",
        csv,
        "manual_trade_journal.csv",
        "text/csv"
    )
else:
    st.info("No manual trades recorded yet.")
