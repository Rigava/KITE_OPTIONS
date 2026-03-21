import streamlit as st
import pandas as pd
import numpy as np
import time
from kiteconnect import KiteTicker, KiteConnect
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ---------------- CONFIG ---------------- #
# Load configuration
default_enctoken = "QATlhG13qRpXA+/9gAHpEeNGdqXE7tSZXa5rXrbTqXwGAOxkik0pBETlgrJb07Md2ElvNL0VEbFt/yGZoqQ9B2xBpNDuNkZcoEaE8nZ/B57zCAf08wughA=="
# ---------------- USER INPUT ---------------- #
st.sidebar.header("🔐 Kite Credentials")

ENCTOKEN = st.sidebar.text_input("ENCTOKEN",value=default_enctoken ,type="password")
USER_ID = st.sidebar.text_input("User ID",value ="ZM1064")
api_key = st.sidebar.text_input("API Key",value="hmoh6luxizaqyl2y")

start_button = st.sidebar.button("🚀 Start Live Data")

# ---------------- VALIDATION ---------------- #
def inputs_valid():
    return all([
        ENCTOKEN is not None and ENCTOKEN != "",
        USER_ID is not None and USER_ID != "",
        api_key is not None and api_key != ""
    ])
INDEX = "NIFTY"
INDEX_TOKEN = 256265


INDEX = "NIFTY"
INDEX_TOKEN = 256265

REFRESH_INTERVAL = 120  # seconds

# ---------------- STATE ---------------- #
if "ltp_data" not in st.session_state:
    st.session_state.ltp_data = {}

if "spot_price" not in st.session_state:
    st.session_state.spot_price = None

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

# ---------------- WEBSOCKET ---------------- #
def start_ws(token_list):

    def on_ticks(ws, ticks):
        for tick in ticks:
            token = tick["instrument_token"]

            if token == INDEX_TOKEN:
                st.session_state.spot_price = tick["last_price"]
            else:
                st.session_state.ltp_data[token] = {
                    "ltp": tick["last_price"],
                    "oi": tick["oi"],
                    "volume": tick.get("volume",0)
                }

    def on_connect(ws, response):
        ws.subscribe(token_list)
        ws.set_mode(ws.MODE_FULL, token_list)

    kws = KiteTicker(api_key, ENCTOKEN + "&user_id=" + USER_ID)

    kws.on_ticks = on_ticks
    kws.on_connect = on_connect

    kws.connect(threaded=True)

# ---------------- BUILD CHAIN ---------------- #
def build_option_chain(options_df):

    live_df = pd.DataFrame(st.session_state.ltp_data).T

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

# ---------------- METRICS ---------------- #
def get_atm(chain, spot):
    chain["dist"] = abs(chain["strike"] - spot)
    return chain.loc[chain.dist.idxmin(), "strike"]

def calculate_pcr(chain):
    return chain["oi_PE"].sum() / chain["oi_CE"].sum()

def atm_straddle(chain, atm):
    row = chain[chain.strike == atm]
    return row["ltp_CE"].values[0] + row["ltp_PE"].values[0]

# ---------------- STREAMLIT UI ---------------- #
st.set_page_config(layout="wide")
st.title("📊 Simple Options Dashboard")

# Load instruments
df = load_instruments()
st.success(f"Loaded all the instruments: {len(df)}")
options_df, expiry = get_weekly_options(df, INDEX)
st.write("Weekly Expiry:", expiry)
st.write("Total Option Contracts:", len(options_df))

# Start websocket only once
if start_button:
    if not inputs_valid():
        st.error("Please enter all credentials before starting.")
        st.stop()
    if "ws_started" not in st.session_state:
        token_list = options_df.instrument_token.tolist()
        token_list.append(INDEX_TOKEN)
        st.write("Total subscribed:", len(token_list))
        start_ws(token_list)
        st.session_state.ws_started = True
        st.success("WebSocket started successfully!")

# Wait for data
if len(st.session_state.ltp_data) == 0:
    st.warning("Waiting for live data...")
    st.stop()

chain = build_option_chain(options_df)

if chain is None or st.session_state.spot_price is None:
    st.warning("Building option chain...")
    st.stop()

# Metrics
spot = st.session_state.spot_price
atm = get_atm(chain, spot)
pcr = calculate_pcr(chain)
straddle = atm_straddle(chain, atm)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Spot", round(spot,2))
col2.metric("ATM", atm)
col3.metric("PCR", round(pcr,2))
col4.metric("Straddle", round(straddle,2))

# Option Chain Table
st.subheader("Option Chain")

st.dataframe(chain[
    ["oi_CE","ltp_CE","strike","ltp_PE","oi_PE"]
].sort_values("strike"))

# Auto refresh
st_autorefresh(interval=REFRESH_INTERVAL * 1000)
