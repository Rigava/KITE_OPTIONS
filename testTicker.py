import streamlit as st
import threading
import time


# 1. Setup Session State to store the latest NIFTY price
if 'nifty_ltp' not in st.session_state:
    st.session_state.nifty_ltp = 0.0
if 'ticker_started' not in st.session_state:
    st.session_state.ticker_started = False

# 2. Define the KiteTicker Callback
def on_ticks(ws, ticks):
    # Update the session state with the new NIFTY price
    # NIFTY 50 instrument token is usually 256265
    for tick in ticks:
        if tick['instrument_token'] == 256265:
            st.session_state.nifty_ltp = tick['last_price']

# 3. Function to start the Ticker in a background thread
def start_kite_ticker(enctoken):
    # Replace with your specific library initialization
    kws = KiteTicker(api_key, ENCTOKEN + "&user_id=" + USER_ID)
    kws.on_ticks = on_ticks
    kws.connect(threaded=True)
    st.session_state.ticker_started = True

# 4. Streamlit UI Layout
st.title("NIFTY 50 Live Tracker")
default_enctoken = "QATlhG13qRpXA+/9gAHpEeNGdqXE7tSZXa5rXrbTqXwGAOxkik0pBETlgrJb07Md2ElvNL0VEbFt/yGZoqQ9B2xBpNDuNkZcoEaE8nZ/B57zCAf08wughA=="
ENCTOKEN = st.text_input("Enter enctoken",value = default_enctoken, type="password")
USER_ID = st.sidebar.text_input("User ID",value ="ZM1064")
api_key = st.secrets['API_KEY']

if st.button("Connect Ticker") and not st.session_state.ticker_started:
    start_kite_ticker(token_input)

# 5. Live Display Loop
placeholder = st.empty()

while st.session_state.ticker_started:
    with placeholder.container():
        st.metric(label="NIFTY 50", value=f"₹ {st.session_state.nifty_ltp}")
    time.sleep(60) # Refresh UI every second
