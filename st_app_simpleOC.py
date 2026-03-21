import streamlit as st
import pandas as pd
import numpy as np
import time
from kiteconnect import KiteTicker, KiteConnect
from datetime import datetime
# from streamlit_autorefresh import st_autorefresh
# ---------------- CONFIG ---------------- #
INDEX = "NIFTY"
INDEX_TOKEN = 256265
REFRESH_INTERVAL = 10  # seconds
STRIKE_RANGE = 500     # +/- range around spot

# ---------------- GLOBAL STORE (THREAD SAFE) ---------------- #
ltp_data_global = {}
spot_price_global = None

if "ws_started" not in st.session_state:
    st.session_state.ws_started = False
    
# ---------------- STREAMLIT UI ---------------- #
st.set_page_config(layout="wide")
st.title("📊 Simple Options Dashboard")
# SIDEBAR ---------------- USER INPUT ---------------- #
default_enctoken = "QATlhG13qRpXA+/9gAHpEeNGdqXE7tSZXa5rXrbTqXwGAOxkik0pBETlgrJb07Md2ElvNL0VEbFt/yGZoqQ9B2xBpNDuNkZcoEaE8nZ/B57zCAf08wughA=="

st.sidebar.header("🔐 Kite Credentials")
ENCTOKEN = st.sidebar.text_input("ENCTOKEN",value=default_enctoken ,type="password")
USER_ID = st.sidebar.text_input("User ID",value ="ZM1064")
API_KEY = st.secrets['API_KEY']

start_button = st.sidebar.button("🚀 Start Live Data")
stop_button = st.sidebar.button("🛑 Stop")


# ---------------- LOAD INSTRUMENTS ---------------- #
@st.cache_data
def load_instruments():
    df = pd.read_csv("https://api.kite.trade/instruments")
    return df

def get_weekly_options(df, index):
    df = df[df["name"] == index]
    expiry = min(df["expiry"].unique())
    df = df[df["expiry"] == expiry]

    return df[["instrument_token","strike","instrument_type"]], expiry

# ---------------- FILTER STRIKES ---------------- #
def filter_strikes(options_df, spot):
    if spot is None:
        return options_df
    return options_df[
        (options_df["strike"] >= spot - STRIKE_RANGE) &
        (options_df["strike"] <= spot + STRIKE_RANGE)
    ]

# ---------------- WEBSOCKET ---------------- #
def start_ws(token_list):

    global ltp_data_global, spot_price_global

    if "kws" in st.session_state:
        return

    def on_ticks(ws, ticks):
        global ltp_data_global, spot_price_global

        for tick in ticks:
            token = tick["instrument_token"]

            if token == INDEX_TOKEN:
                spot_price_global = tick["last_price"]
            else:
                ltp_data_global[token] = {
                    "ltp": tick["last_price"],
                    "oi": tick["oi"],
                    "volume": tick.get("volume", 0)
                }

    def on_connect(ws, response):
        ws.subscribe(token_list)
        ws.set_mode(ws.MODE_FULL, token_list)

    def on_close(ws, code, reason):
        print(f"Closed: {code} - {reason}")
        st.session_state.ws_started = False

    kws = KiteTicker(API_KEY, ENCTOKEN + "&user_id=" + USER_ID)
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close
    kws.connect(threaded=True)
    st.session_state.kws = kws

# ---------------- STOP WS ---------------- #
def stop_ws():
    if "kws" in st.session_state:
        try:
            st.session_state.kws.close()
        except:
            pass
        del st.session_state.kws

    st.session_state.ws_started = False

# ---------------- VALIDATION ---------------- #
def inputs_valid():
    return all([ENCTOKEN, USER_ID, API_KEY])

# ---------------- CONTROL FLOW ---------------- #
if start_button:
    if not inputs_valid():
        st.error("Please enter all credentials")
        st.stop()

    if not st.session_state.ws_started:

        df = load_instruments()
        options_df, expiry = get_weekly_options(df, INDEX)

        token_list = options_df.instrument_token.tolist()
        token_list.append(INDEX_TOKEN)

        start_ws(token_list)

        st.session_state.ws_started = True
        st.success("WebSocket started")

if stop_button:
    stop_ws()
    st.warning("WebSocket stopped")
    st.stop()

# ---------------- BLOCK BEFORE START ---------------- #
if not st.session_state.ws_started:
    st.info("Enter credentials and click Start")
    st.stop()

# ---------------- AUTO REFRESH ---------------- #
# st_autorefresh(interval=REFRESH_INTERVAL * 1000, key="refresh")

# ---------------- LOAD DATA ---------------- #
df = load_instruments()
options_df, expiry = get_weekly_options(df, INDEX)

# Wait for data
if len(ltp_data_global) == 0:
    st.warning("Waiting for live data...")
    st.stop()

if spot_price_global is None:
    st.warning("Waiting for spot price...")
    st.stop()

# Apply strike filter AFTER spot available
options_df = filter_strikes(options_df, st.session_state.spot_price)

# ---------------- BUILD OPTION CHAIN ---------------- #
def build_option_chain(options_df):

    live_df = pd.DataFrame(ltp_data_global).T

    if len(live_df) == 0:
        return None

    live_df = live_df.reset_index().rename(columns={"index":"instrument_token"})
    live_df["instrument_token"] = live_df["instrument_token"].astype("int64")

    df = options_df.merge(live_df, on="instrument_token", how="left")

    ce = df[df.instrument_type=="CE"].rename(columns={
        "ltp":"ltp_CE","oi":"oi_CE","volume":"volume_CE"
    })

    pe = df[df.instrument_type=="PE"].rename(columns={
        "ltp":"ltp_PE","oi":"oi_PE","volume":"volume_PE"
    })

    chain = ce.merge(pe, on="strike")

    return chain.sort_values("strike")

chain = build_option_chain(options_df)

if chain is None:
    st.warning("Building option chain...")
    st.stop()

# ---------------- METRICS ---------------- #
def get_atm(chain, spot):
    chain["dist"] = abs(chain["strike"] - spot)
    return chain.loc[chain.dist.idxmin(), "strike"]

def calculate_pcr(chain):
    ce = chain["oi_CE"].sum()
    pe = chain["oi_PE"].sum()
    return pe / ce if ce != 0 else None

def atm_straddle(chain, atm):
    row = chain[chain.strike == atm]
    return row["ltp_CE"].values[0] + row["ltp_PE"].values[0]

spot = spot_price_global
atm = get_atm(chain, spot)
pcr = calculate_pcr(chain)
straddle = atm_straddle(chain, atm)

# ---------------- UI ---------------- #
col1, col2, col3, col4 = st.columns(4)

col1.metric("Spot", round(spot,2))
col2.metric("ATM", atm)
col3.metric("PCR", round(pcr,2) if pcr else "-")
col4.metric("Straddle", round(straddle,2))

# ---------------- TABLE ---------------- #
st.subheader("Option Chain")

st.dataframe(
    chain[["oi_CE","ltp_CE","strike","ltp_PE","oi_PE"]],
    use_container_width=True
)
