import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, time, timedelta
import plotly.graph_objects as go

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
        background-color: var(--card-bg);
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
    /* Dark mode colors */
    :root {
        --card-bg: #f9fafb;
        --bg-color: white;
        --text-color: #111;
    }
    .dark-mode {
        --card-bg: #1e1e1e;
        --bg-color: #121212;
        --text-color: #eee;
    }
    .dark-mode .card {
        box-shadow: 0 3px 8px rgba(255 255 255 / 0.1);
    }
    body {
        background-color: var(--bg-color);
        color: var(--text-color);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# -------------------------------
# DARK MODE TOGGLE
# -------------------------------
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

def toggle_dark_mode():
    st.session_state.dark_mode = not st.session_state.dark_mode

with st.sidebar:
    st.checkbox("🌙 Dark Mode", value=st.session_state.dark_mode, key="dark_mode_checkbox", on_change=toggle_dark_mode)

if st.session_state.dark_mode:
    st.markdown('<body class="dark-mode">', unsafe_allow_html=True)
else:
    st.markdown('<body>', unsafe_allow_html=True)

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

@st.cache_data
def get_asset_info(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info.get('longName', symbol)
    except Exception:
        return symbol

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

# Load data and asset name
df = load_data(symbol)
asset_name = get_asset_info(symbol)

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
with st.container():
    col_keylevels, col_auto = st.columns([1,1], gap="large")

    # Key Levels + Asset Name Card
    with col_keylevels:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f"## 📌 {asset_name} - Key Levels")

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

        # Plot Price Chart + Levels
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f"## 📈 Price Chart with Levels")

        fig = go.Figure()

        # Price Candles
        fig.add_trace(go.Candlestick(
            x=df["time"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
            increasing_line_color='#22c55e' if not st.session_state.dark_mode else '#4ade80',
            decreasing_line_color='#ef4444' if not st.session_state.dark_mode else '#f87171',
            increasing_fillcolor='rgba(34,197,94,0.3)' if not st.session_state.dark_mode else 'rgba(74,222,128,0.3)',
            decreasing_fillcolor='rgba(239,68,68,0.3)' if not st.session_state.dark_mode else 'rgba(248,113,113,0.3)',
        ))

        # Add horizontal lines for levels if available
        level_lines = {
            "OH": OH,
            "OL": OL,
            "PMH": PMH,
            "PML": PML,
            "PDH": PDH,
            "PDL": PDL,
            "PDO": PDO
        }
        colors = {
            "OH": "purple",
            "OL": "purple",
            "PMH": "blue",
            "PML": "blue",
            "PDH": "orange",
            "PDL": "orange",
            "PDO": "gray"
        }

        for lvl_name, lvl_value in level_lines.items():
            if lvl_value is not None:
                fig.add_hline(
                    y=lvl_value,
                    line_dash="dot",
                    line_color=colors[lvl_name],
                    annotation_text=lvl_name,
                    annotation_position="top left",
                    annotation_font_color=colors[lvl_name],
                )

        fig.update_layout(
            height=350,
            margin=dict(l=10, r=10, t=25, b=10),
            paper_bgcolor='var(--card-bg)',
            plot_bgcolor='var(--card-bg)',
            font_color='var(--text-color)',
            xaxis_rangeslider_visible=False,
            xaxis_title="Time",
            yaxis_title="Price",
        )

        st.plotly_chart(fig, use_container_width=True)
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

    # Manual Replay Card with Animated Slider
    with col_manual:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("## 🎮 Manual Trading Replay")

        if 'df_replay' not in st.session_state:
            st.session_state.df_replay = df.copy()
        if 'index' not in st.session_state:
            st.session_state.index = 0
        if '
