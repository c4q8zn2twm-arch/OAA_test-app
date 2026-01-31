import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, time

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(page_title="Trading Replay Pro", layout="wide")

# =====================================================
# DARK MODE TOGGLE
# =====================================================
dark_mode = st.sidebar.toggle("🌙 Dark Mode", value=True)
PLOT_THEME = "plotly_dark" if dark_mode else "plotly_white"

bg_color = "#0e1117" if dark_mode else "#f5f7fa"
card_color = "#161b22" if dark_mode else "#ffffff"
text_color = "#ffffff" if dark_mode else "#000000"

st.markdown(
    f"""
    <style>
        body {{
            background-color: {bg_color};
            color: {text_color};
        }}
        .card {{
            background-color: {card_color};
            padding: 1.2rem;
            border-radius: 12px;
            margin-bottom: 1rem;
        }}
    </style>
    """,
    unsafe_allow_html=True
)

# =====================================================
# HEADER BAR
# =====================================================
top_l, top_r = st.columns([3, 1])

with top_l:
    st.title("📈 Trading Replay & Backtester")

with top_r:
    st.markdown(
        f"**🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**",
        unsafe_allow_html=True
    )

# =====================================================
# SYMBOL INPUT + HINTS
# =====================================================
st.sidebar.subheader("🔎 Market Selection")
symbol = st.sidebar.text_input("Symbol", "AAPL")

st.sidebar.info(
    """
**Supported Symbols**
- Stocks: `AAPL`, `MSFT`, `GOOGL`
- Crypto: `BTC-USD`, `ETH-USD`
- FX: `EURUSD=X`, `USDJPY=X`
"""
)

# =====================================================
# DATA LOADER
# =====================================================
@st.cache_data
def load_data(sym):
    df = yf.download(
        sym,
        interval="5m",
        period="5d",
        auto_adjust=False,
        progress=False
    )

    if df.empty:
        return df

    df = df.reset_index()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    df.rename(columns={"Datetime": "time", "Date": "time"}, inplace=True)
    df["time"] = pd.to_datetime(df["time"])
    return df

df = load_data(symbol)

if df.empty:
    st.error("No data returned.")
    st.stop()

# =====================================================
# LEVEL CALCULATIONS
# =====================================================
def opening_range(df):
    o = df[df["time"].dt.time <= time(9, 35)]
    return (o.High.max(), o.Low.min()) if not o.empty else (None, None)

def prior_day_levels(df):
    df["date"] = df["time"].dt.date
    dates = sorted(df.date.unique())
    if len(dates) < 2:
        return None, None
    prior = df[df.date == dates[-2]]
    return prior.High.max(), prior.Low.min()

OH, OL = opening_range(df)
PDH, PDL = prior_day_levels(df)

# =====================================================
# ASSET TITLE + LEVELS
# =====================================================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader(f"📌 {symbol.upper()} — Key Levels")

if OH is None:
    st.warning("Aftermarket / No opening data available.")
else:
    st.write({
        "Opening High": OH,
        "Opening Low": OL,
        "Prior Day High": PDH,
        "Prior Day Low": PDL
    })

st.markdown('</div>', unsafe_allow_html=True)

# =====================================================
# PRICE CHART
# =====================================================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("📊 Price Chart")

fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=df["time"],
    open=df["Open"],
    high=df["High"],
    low=df["Low"],
    close=df["Close"],
    name="Price"
))

def add_level(y, name, color):
    if y is not None:
        fig.add_hline(y=y, line_dash="dot", line_color=color, annotation_text=name)

add_level(OH, "OH", "green")
add_level(OL, "OL", "red")
add_level(PDH, "PDH", "blue")
add_level(PDL, "PDL", "orange")

fig.update_layout(
    template=PLOT_THEME,
    height=520,
    xaxis=dict(
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1D", step="day", stepmode="backward"),
                dict(count=2, label="2D", step="day", stepmode="backward"),
                dict(count=5, label="5D", step="day", stepmode="backward"),
                dict(step="all")
            ])
        ),
        rangeslider=dict(visible=True),
        type="date"
    )
)

st.plotly_chart(fig, use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

# =====================================================
# AUTOMATED SIGNALS
# =====================================================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("🤖 Automated Trade Suggestions")

signals = []

for i in range(1, len(df)):
    c = df.iloc[i]
    p = df.iloc[i - 1]

    if OH and c.Close > OH and c.Close > p.High:
        signals.append({
            "Time": c.time,
            "Side": "LONG",
            "Entry": c.Close,
            "Target": PDH,
            "Stop": OL
        })

    if OH and c.High > OH and c.Close < OH:
        signals.append({
            "Time": c.time,
            "Side": "SHORT",
            "Entry": c.Close,
            "Target": PDL,
            "Stop": c.High
        })

sig_df = pd.DataFrame(signals)
st.dataframe(sig_df, use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

# =====================================================
# MANUAL REPLAY (UNCHANGED LOGIC + PREV BUTTON)
# =====================================================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("🎮 Manual Replay")

if "index" not in st.session_state:
    st.session_state.index = 0
if "position" not in st.session_state:
    st.session_state.position = None
if "trades" not in st.session_state:
    st.session_state.trades = []

idx = st.slider(
    "Replay Position",
    0, len(df) - 1,
    st.session_state.index
)
st.session_state.index = idx
row = df.iloc[idx]

st.write({
    "Time": row.time,
    "Open": row.Open,
    "High": row.High,
    "Low": row.Low,
    "Close": row.Close
})

c1, c2, c3, c4 = st.columns(4)

with c1:
    if st.button("⏮ Previous"):
        st.session_state.index = max(0, idx - 1)

with c2:
    if st.button("⏭ Next"):
        st.session_state.index = min(len(df) - 1, idx + 1)

with c3:
    if st.button("🟢 Buy") and st.session_state.position is None:
        st.session_state.position = {"entry": row.Close, "time": row.time}

with c4:
    if st.button("🔴 Sell") and st.session_state.position:
        st.session_state.trades.append({
            "Entry": st.session_state.position["entry"],
            "Exit": row.Close,
            "PnL": row.Close - st.session_state.position["entry"],
            "Time": row.time
        })
        st.session_state.position = None

st.markdown('</div>', unsafe_allow_html=True)

# =====================================================
# JOURNAL WITH DELETE CONFIRMATION
# =====================================================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("📒 Manual Trade Journal")

if st.session_state.trades:
    jdf = pd.DataFrame(st.session_state.trades)
    jdf["Delete"] = False

    edited = st.data_editor(jdf, use_container_width=True)

    if st.button("🗑 Delete Selected"):
        st.session_state.confirm_delete = True

    if st.session_state.get("confirm_delete"):
        if st.checkbox("Confirm deletion"):
            st.session_state.trades = edited[~edited.Delete].drop(columns="Delete").to_dict("records")
            st.success("Deleted selected trades.")
            st.session_state.confirm_delete = False
else:
    st.info("No manual trades recorded.")

st.markdown('</div>', unsafe_allow_html=True)
