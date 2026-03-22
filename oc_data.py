import streamlit as st
from kiteconnect import KiteTicker
import time
import json
import pandas as pd
import sys
import os
from datetime import datetime
from option_chain import build_option_chain, create_option_chain
from metrics import get_atm_strike,atm_window,atm_straddle,calculate_pcr, get_max_pain
#Set streamlit wide
st.set_page_config(layout="wide")

def save_snapshot(existing_df, df):
    if df is None or len(df) == 0:
        return existing_df
    df = df.copy()
    if existing_df is None or len(existing_df) == 0:
        return df
    return pd.concat([existing_df, df], ignore_index=True)
# 👉 Persist Across Streamlit Reruns--Streamlit rerun will wipe your dataframe
if "history_df" not in st.session_state:
    st.session_state.history_df = pd.DataFrame()

# Load configuration
ltp_data = {}
spot_price = None
# 4. Streamlit UI INPUT Layout
st.title("NIFTY 50 Live Tracker")
default_enctoken = "QATlhG13qRpXA+/9gAHpEeNGdqXE7tSZXa5rXrbTqXwGAOxkik0pBETlgrJb07Md2ElvNL0VEbFt/yGZoqQ9B2xBpNDuNkZcoEaE8nZ/B57zCAf08wughA=="
ENCTOKEN = st.sidebar.text_input("Enter enctoken",value = default_enctoken, type="password")
USER_ID = st.sidebar.text_input("User ID")
api_key = st.secrets['API_KEY']
# with open("loginCredential.json") as f:
#     login_credential = json.load(f)
# api_key = login_credential["api_key"]
INDEX = "NIFTY"
INDEX_TOKEN = 256265
df = pd.read_csv("https://api.kite.trade/instruments")
print("Total instruments:", len(df))

#Create a function to filter weekly options for the given index
def get_weekly_options(df, index):
    df = df[df["name"] == index]
    expiries = list(df["expiry"].unique())
    current_expiry = min(expiries)
    df = df[df["expiry"] == current_expiry]
    df = df.reset_index(drop=True)
    df = df[["instrument_token","strike","instrument_type","expiry"]]
    return df, current_expiry
#Create weekly options for the index
options_df, expiry = get_weekly_options(df, index=INDEX)
print("Weekly Expiry:", expiry)
print("Total Option Contracts:", len(options_df))
#create a list of instrument tokens to subscribe for live data
token_list = options_df.instrument_token.tolist()
token_list.append(INDEX_TOKEN)
print("Total subscribed tokens:", len(token_list))

def on_ticks(ws, ticks):
    global ltp_data, spot_price
    for tick in ticks:
        token = tick["instrument_token"]
        if token == INDEX_TOKEN:
            spot_price = tick["last_price"]
        else:
            ltp_data[token] = {
                "ltp": tick["last_price"],
                "oi": tick["oi"],
                "volume": tick.get("volume", 0),
            }

def on_connect(ws, response):
    ws.subscribe(token_list)
    ws.set_mode(ws.MODE_FULL, token_list)

kws = KiteTicker(api_key=api_key, access_token=ENCTOKEN + "&user_id=" + USER_ID)

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.connect(threaded=True)



# 5. Live Display Loop
placeholder = st.empty()
# exist_df = st.session_state.history_df
exist_df = pd.DataFrame()
#refresh every 5 minutes# st_autorefresh(interval=1 * 60 * 1000, key="global_refresh")
while True:
        
    with placeholder.container():
        st.metric(label="NIFTY 50", value=f"₹ {spot_price}")

    chain = build_option_chain(options_df, ltp_data)
    if chain is None: 
        time.sleep(5) 
        continue

    oc = create_option_chain(chain)

    pcr = calculate_pcr(oc)
    max_pain = get_max_pain(oc)

    # Determine ATM using the live spot price. get_atm_strike returns None
    # if spot_price is not yet available, so guard the downstream calls.
    atm = get_atm_strike(oc, spot_price)
    if atm is not None:
        atm_chain = atm_window(oc, atm, n=10)
        pcr_atm_chain = calculate_pcr(atm_chain)
        straddle = atm_straddle(oc, atm)
    else:
        atm_chain = None
        pcr_atm_chain = None
        straddle = None
    atm_chain["timestamp"] = datetime.now()
    atm_chain["spot"] = spot_price
    atm_chain["max_pain"] = max_pain
    exist_df= save_snapshot(exist_df, atm_chain)
    with st.expander(f"ATM contracts{datetime.now()}"):
        st.dataframe(atm_chain)
    with st.expander("ALL ATM contracts"):
        st.dataframe(exist_df)
    # print("Saved snapshot")
    st.write("\n------", datetime.now(), "------")
    st.write("Spot:", round(spot_price,2))
    st.write("ATM:", atm)
    st.write("Max Pain:", max_pain)
    st.write("PCR Overall:", round(pcr,2) if pcr is not None else None)
    st.write("PCR ATM Window:", round(pcr_atm_chain,2) if pcr_atm_chain is not None else None)
    st.write("Straddle:", round(straddle,2) if straddle is not None else None)
    #================================ Strike selector Trends========================================
    st.subheader(f"ATMStrike {atm}")
    strike_df = exist_df[exist_df["strike"] == atm].sort_values("timestamp")
    st.write("Price Trend")
    st.line_chart(strike_df.set_index("timestamp")[["ltp_CE","ltp_PE"]])
    st.write("OI Trend")
    trend = strike_df.set_index("timestamp")[["oi_CE","oi_PE"]]
    st.line_chart(trend)
    time.sleep(10)


# Final working pattern
# Websocket → ltp_data (global)
# Streamlit refresh → compute → append → session_state           ↓
# Persistent time-series dataframe 
