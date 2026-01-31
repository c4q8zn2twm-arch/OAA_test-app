import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, time, timedelta

st.set_page_config(layout="wide", page_title="Opening Auction Acceptance + Manual Replay")

# --- CUSTOM CSS FOR CARDS & COLORS ---
st.markdown(
    """
    <style>
    /* General font */
    .streamlit-expanderHeader {
        font-weight: 600 !important;
        font-size: 1.2rem !important;
    }
    .stTextInput>div>div>input {
        font-size: 1.1rem !important;
        padding: 0.5rem !important;
    }
    /* Cards */
    .card {
        background-color: #f9fafb;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 3px 8px rgb(0 0 0 / 0.1);
    }
    /* Badges */
    .badge {
        display: inline-block;
        padding: 0.3em 0.8em;
        font-weight: 600;
        border-radius: 12px;
        color: white;
        font-size: 0.9rem;
        user-select: none;
    }
    .badge.initiative { background-color: #16a34a; }  /* Green */
    .badge.rotational { background-color: #f97316; }  /* Orange */
    .badge.long { background-color: #22c55e; }        /* Green */
    .badge.short { background-color: #ef4444; }       /* Red */
    /* Headers */
    h2, h3 {
        font-weight: 700 !important;
    }
    /* Sidebar tweaks */
    .sidebar .stTextInput>div>div>input {
        font-size: 1.1rem !important;
        padding: 0.5rem !important;
    }
    .sidebar .stMarkdown {
        font-size: 0.95rem !important;
        margin-bottom: 1rem;
    }
    /* Data Editor tweaks */
    .dataframe-container {
        margin-top: 0.5rem;
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True
)

# -------------------------------
# DATA LOADER
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
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    if "Datetime" in df.columns:
        df.rename(columns={"Datetime": "time"}, inplace=True)
    elif "Date" in df.columns:
        df.rename(columns={"Date": "time"}, inplace=True)
    elif "time" not in df.columns:
        return pd.DataFrame()
    df["time"] = pd.to_datetime(df["time"])
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
    weekday = last_datetime.weekday()  # Mon=0, Sun=6
    if weekday == 0:  # Monday
        prior_date = last_datetime - timedelta(days=3)
    elif weekday == 5:  # Sat
        prior_date = last_datetime - timedelta(days=1)
    elif weekday == 6:  # Sun
        prior_date = last_datetime - timedelta(days=2)
    else:
        prior_date = last_datetime - timedelta(days=1)
    available_prior_dates = [d for d in dates if d < prior_date.date()]
    if available_prior_dates:
        prior_date = max(available_prior_dates)
    else:
        prior_date = dates[-2]
    prior = df[df["date"] == prior_date]
    if prior.empty:
        return None, None, None
    return prior["High"].max(), prior["Low"].min(), prior["Open"].iloc[0]

def rr(entry, stop, target):
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return round(reward / risk, 2) if risk > 0 else 0

# -------------------------------
# SIDEBAR - Symbol Input, Time, Day Type
# -------------------------------
with st.sidebar:
    st.header("🔍 Symbol & Info")
    symbol = st.text_input("Symbol (Stocks / FX / Crypto)", "AAPL")
    st.markdown(
        """
        **Symbol Hint:**  
        Use tickers like `AAPL` (stocks), `EURUSD=X` (Forex), `BTC-USD` (Crypto), `ES=F` (Futures)
        """
    )
    now = datetime.now()
    st.markdown(f"### ⏰ Current Time\n**{now.strftime('%Y-%m-%d %H:%M:%S')}**")

# Load data (in main area, but symbol chosen in sidebar)
df = load_data(symbol)

if df.empty:
    st.error("No data returned. Check symbol or market hours.")
    st.stop()

# Calculate key levels
OH, OL = opening_range(df)
PMH, PML = premarket_levels(df)
PDH, PDL, PDO = prior_day_levels(df)

# Determine day type
latest = df.iloc[-1]
day_type = "Rotational"
if OH is not None and OL is not None:
    if latest["Close"] > OH or latest["Close"] < OL:
        day_type = "Initiative"

# Manual override in sidebar
with st.sidebar:
    manual_day = st.selectbox("Day Type Override", ["Auto", "Initiative", "Rotational"])
if manual_day != "Auto":
    day_type = manual_day

# Show day type badge in sidebar
badge_class = "initiative" if day_type == "Initiative" else "rotational"
st.sidebar.markdown(f'<div class="badge {badge_class}">Day Type: {day_type}</div>', unsafe_allow_html=True)

# -------------------------------
# MAIN PAGE LAYOUT
# -------------------------------
# Container for all main content
with st.container():
    # Top half: Key Levels + Automated Suggestions side-by-side
    col_keylevels, col_auto = st.columns([1,1], gap="large")

    # Key Levels Card
    with col_keylevels:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("## 🔑 Key Levels")
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
        st.markdown('</div>', unsafe_allow_html=True)

    # Automated Trade Suggestions + Journal Card
    with col_auto:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("## 🤖 Trade Suggestions & Automated Journal")

        signals = []
        if OH is None or OL is None:
            st.info("No opening range data available, so no trade signals generated.")
        else:
            for i in range(5, len(df)):
                candle = df.iloc[i]
                prev = df.iloc[i-1]
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

            # Colorize Side column
            def side_colored(val):
                color = "#22c55e" if val == "Long" else "#ef4444"
                return f'<span style="color:{color}; font-weight:700;">{val}</span>'

            journal_df_display = journal_df.copy()
            journal_df_display["Side"] = journal_df_display["Side"].apply(
                lambda x: f'<span style="color:{"#22c55e" if x=="Long" else "#ef4444"}; font-weight:700;">{x}</span>'
            )

            edited_df = st.data_editor(
                journal_df,
                use_container_width=True,
                column_config={
                    "Delete": st.column_config.CheckboxColumn("Delete"),
                    "DateTime": st.column_config.DateTimeColumn("Date/Time"),
                },
                num_rows="dynamic"
            )

            col1, col2, col3 = st.columns([1,1,1])

            with col1:
                if st.button("🗑️ Delete Selected Automated Entries"):
                    st.session_state.show_auto_confirm = True

            with col2:
                if st.button("⬇ Export Automated Journal CSV"):
                    export_df = st.session_state.automated_journal.drop(columns=["Delete"], errors="ignore")
                    export_df.to_csv("oaa_journal.csv", index=False)
                    st.success("Exported oaa_journal.csv")

            if st.session_state.get("show_auto_confirm", False):
                confirm = st.checkbox("Confirm deletion of selected automated entries")
                if confirm:
                    st.session_state.automated_journal = edited_df[~edited_df["Delete"].fillna(False)].reset_index(drop=True)
                    st.success("Deleted selected automated entries.")
                    st.session_state.show_auto_confirm = False

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    # Bottom half: Manual Replay + Trade Journals side-by-side
    col_manual, col_journals = st.columns([1,1], gap="large")

    # Manual Replay Card
    with col_manual:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("## 🎮 Manual Trading Replay")

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

        st.markdown(f"### Candle {idx + 1} / {len(df_replay)}")
        st.write({
            "Date": row["time"],
            "Open": round(row.Open, 2),
            "High": round(row.High, 2),
            "Low": round(row.Low, 2),
            "Close": round(row.Close, 2),
        })

        col1, col2, col3, col4, col5 = st.columns(5, gap="small")

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
            st.text_area(
                "📝 Trade Note",
                st.session_state.position.get("note", ""),
                key="trade_note_textarea",
                on_change=lambda: st.session_state.position.update({"note": st.session_state.trade_note_textarea}),
                height=80,
            )

        st.markdown('</div>', unsafe_allow_html=True)

    # Trade Journals Card (Manual)
    with col_journals:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("## 📒 Manual Trade Journal")

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

            col1, col2, col3 = st.columns([1,1,1])

            with col1:
                if st.button("🗑️ Delete Selected Manual Entries"):
                    st.session_state.show_manual_confirm = True

            with col2:
                csv = pd.DataFrame(st.session_state.trades).to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇ Export Manual Trades CSV",
                    csv,
                    "manual_trade_journal.csv",
                    "text/csv"
                )

            if st.session_state.get("show_manual_confirm", False):
                confirm_manual = st.checkbox("Confirm deletion of selected manual entries")
                if confirm_manual:
                    st.session_state.trades = edited_manual_df[~edited_manual_df["Delete"].fillna(False)].drop(columns=["Delete"]).to_dict('records')
                    st.success("Deleted selected manual entries.")
                    st.session_state.show_manual_confirm = False
        else:
            st.info("No manual trades recorded yet.")

        st.markdown('</div>', unsafe_allow_html=True)
