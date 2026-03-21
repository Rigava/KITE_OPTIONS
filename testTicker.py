import streamlit as st
import threading
import time
from kiteconnect import KiteTicker, KiteConnect

# 1. Setup Session State to store the latest NIFTY price
ltp_data = None
if 'ticker_started' not in st.session_state:
    st.session_state.ticker_started = False
# 1b. Configuration & Constants
NIFTY_SYMBOL = "NSE:NIFTY 50"
NIFTY_TOKEN = 256265
# 2. Define the KiteTicker Callback

def on_ticks(ws, ticks):
    # Update the session state with the new NIFTY price
    global ltp_data
    for tick in ticks:
        if tick['instrument_token'] == [NIFTY_TOKEN]:
            ltp_data = tick['last_price']
def on_connect(ws, response):
    # This MUST be called to start receiving data
    ws.subscribe([NIFTY_TOKEN])
    ws.set_mode(ws.MODE_LTP, [NIFTY_TOKEN])

# 3. Function to start the Ticker in a background thread
def start_kite_ticker(enctoken):
    # Replace with your specific library initialization
    kws = KiteTicker(api_key, ENCTOKEN + "&user_id=" + USER_ID)
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.connect(threaded=True)
    st.session_state.ticker_started = True

# 4. Streamlit UI Layout
st.title("NIFTY 50 Live Tracker")
default_enctoken = "QATlhG13qRpXA+/9gAHpEeNGdqXE7tSZXa5rXrbTqXwGAOxkik0pBETlgrJb07Md2ElvNL0VEbFt/yGZoqQ9B2xBpNDuNkZcoEaE8nZ/B57zCAf08wughA=="
ENCTOKEN = st.sidebar.text_input("Enter enctoken",value = default_enctoken, type="password")
USER_ID = st.sidebar.text_input("User ID",value ="ZM1064")
api_key = st.secrets['API_KEY']

if st.button("Connect Ticker") and st.session_state.ticker_started:
    start_kite_ticker(ENCTOKEN)
    print(ltp_data)

# 5. Live Display Loop
placeholder = st.empty()

while st.session_state.ticker_started:
    with placeholder.container():
        st.metric(label="NIFTY 50", value=f"₹ {ltp_data}")
    time.sleep(60) # Refresh UI every second
