import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, time, timedelta
import plotly.graph_objects as go

st.set_page_config(page_title="Trading Replay + Signals", layout="wide")

# ----------------------------------
# DATA LOADER
# ----------------------------------
@st.cache_data
def load_data(symbol, interval):
    df = yf.download(
        symbol,
        interval=interval,
        period="7d",
        prepost=True,
        progress=False
    )
    if df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df.rename(columns={"Datetime": "time", "Date": "time"}, inplace=True)
    df["time"] = pd.to_datetime(df["time"])
    df["date"] = df["time"].dt.date
    df["session"] = df["time"].dt.time
    return df

# ----------------------------------
# HERDER + GLOBAL INPUTS
# ----------------------------------
col1, col2 = st.columns([3,1])
with col1:
    st.title("📈 Trading Replay + Signal Suite")
with col2:
    st.markdown(f"**🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")

symbol = st.text_input("Symbol", "AAPL")
interval_map = {"5m":"5m", "15m":"15m", "30m":"30m", "1h":"60m"}
timeframe = st.selectbox("Timeframe", list(interval_map.keys()))
interval = interval_map[timeframe]

try:
    df = load_data(symbol, interval)
    if df.empty:
        st.error("No data returned.")
        st.stop()
except Exception as e:
    st.error("Error loading symbol data.")
    st.stop()

# ----------------------------------
# LEVEL CALCULATIONS
# ----------------------------------
def opening_range(data):
    or_df = data[(data["session"]>=time(9,30)) & (data["session"]<=time(9,35))]
    return or_df.High.max(), or_df.Low.min() if not or_df.empty else (None,None)

def premarket_levels(data):
    pm = data[data["session"]<time(9,30)]
    return pm.High.max(), pm.Low.min() if not pm.empty else (None,None)

def prior_day_levels(data):
    dates = sorted(data["date"].unique())
    if len(dates)<2: return (None,None,None)
    prior = data[data["date"]==dates[-2]]
    return prior.High.max(), prior.Low.min(), prior.Open.iloc[0]

OH, OL = opening_range(df)
PMH, PML = premarket_levels(df)
PDH, PDL, PDO = prior_day_levels(df)

# ----------------------------------
# CHART PANEL
# ----------------------------------
def draw_chart(data):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=data["time"], open=data["Open"],
        high=data["High"], low=data["Low"], close=data["Close"]
    ))
    for lvl, label in [(OH,"OH"),(OL,"OL"),(PMH,"PMH"),(PML,"PML")]:
        if lvl is not None: fig.add_hline(y=lvl, line_dash="dot", annotation_text=label)
    fig.update_layout(
        height=450, xaxis_rangeslider_visible=False
    )
    st.plotly_chart(fig, use_container_width=True)

# ----------------------------------
# SIGNAL ENGINE
# ----------------------------------
def get_signals(data):
    sigs=[]
    def rr(e,s,t): return round(abs(t-e)/abs(e-s),2) if abs(e-s)>0 else 0
    for i in range(5,len(data)):
        c, p = data.iloc[i], data.iloc[i-1]
        if OH and OL and PDH:
            if c.Close > OH and c.Close > p.High:
                r = rr(c.Close,OL,PDH)
                if r>=1: sigs.append({"Type":"OAA-I","Side":"LONG","Time":c.time,
                                      "Entry":c.Close,"Stop":OL,"Target":PDH,"RR":r})
        if OH and PDO:
            if c.High>OH and c.Close<OH:
                r=rr(c.Close,c.High, PDO)
                if r>=1: sigs.append({"Type":"OAA-R","Side":"SHORT","Time":c.time,
                                      "Entry":c.Close,"Stop":c.High,"Target":PDO,"RR":r})
    return pd.DataFrame(sigs)

# ----------------------------------
# VIEW MODES
# ----------------------------------
mode = st.radio("View Mode", ["Automatic Only","Manual Only","Both"], horizontal=True)

# ----------------------------------
# AUTOMATED VIEW
# ----------------------------------
signals_df = get_signals(df)

if mode in ["Automatic Only","Both"]:
    with st.expander("📡 Automated Signals", expanded=True):
        if signals_df.empty:
            st.info("No valid signals.")
        else:
            def highlight_rr(row):
                return ["background-color: lightgreen"]*len(row) if row["RR"]>=2 else [""*len(row)]
            st.dataframe(signals_df.style.apply(highlight_rr,axis=1))

# ----------------------------------
# MANUAL REPLAY
# ----------------------------------
if "idx" not in st.session_state: st.session_state.idx = 0
if "position" not in st.session_state: st.session_state.position = None
if "trades" not in st.session_state: st.session_state.trades = []

if mode in ["Manual Only","Both"]:
    with st.expander("🎮 Manual Replay", expanded=True):
        idx = st.slider("Replay Index",0,len(df)-1, st.session_state.idx)
        st.session_state.idx = idx
        row = df.iloc[idx]
        st.write({
            "Time":row.time,"Open":row.Open,"High":row.High,
            "Low":row.Low,"Close":row.Close
        })
        c1,c2,c3,c4=st.columns(4)
        with c1:
            if st.button("⏮ Previous"): st.session_state.idx=max(0,idx-1)
        with c2:
            if st.button("⏭ Next"): st.session_state.idx=min(len(df)-1,idx+1)
        with c3:
            if st.button("🟢 Buy") and not st.session_state.position:
                st.session_state.position={"entry_time":row.time,"entry_price":row.Close,"note":""}
        with c4:
            if st.button("🔴 Sell") and st.session_state.position:
                t=st.session_state.position
                t["exit_time"]=row.time; t["exit_price"]=row.Close
                t["pnl"]=round(row.Close - t["entry_price"],2)
                st.session_state.trades.append(t)
                st.session_state.position=None

        if st.session_state.position:
            st.session_state.position["note"] = st.text_input(
                "📝 Trade Note", st.session_state.position.get("note","")
            )

# ----------------------------------
# JOURNAL
# ----------------------------------
st.divider()
st.subheader("📒 Trade Journal")

if st.session_state.trades:
    jdf = pd.DataFrame(st.session_state.trades)
    jdf["Delete"] = False
    edited = st.data_editor(jdf,use_container_width=True)
    if st.button("⚠ Confirm Delete"):
        st.session_state.trades = [
            r for i,r in enumerate(st.session_state.trades)
            if not edited.loc[i,"Delete"]
        ]
        st.success("Deleted selected trades")
    st.download_button("⬇ Export CSV",
                       pd.DataFrame(st.session_state.trades).to_csv(index=False),
                       "trade_journal.csv","text/csv")
else:
    st.info("No trades recorded yet.")
