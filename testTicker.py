import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(layout="wide")

st.title("📊 Options Flow Terminal (Advanced)")

# =========================
# FILE UPLOAD
# =========================
uploaded_file = st.file_uploader("Upload Options Data CSV", type=["csv"])

if uploaded_file is None:
    st.info("Please upload a CSV file to proceed.")
    st.stop()

# =========================
# SIDEBAR CONFIG-1
# =========================
st.sidebar.header("⚙️ Settings")
window = st.sidebar.slider("Rolling Window", 3, 30, 5)

# =========================
# FLOW CLASSIFIERS
# =========================
def classify_flow_ce(row):
    oi = row["oi_ce_roll"]
    price = row["price_ce_roll"]

    if oi > 0 and price > 0:
        return "CALL_BUY"        # aggressive bearish
    elif oi > 0 and price < 0:
        return "CALL_WRITE"      # resistance building
    elif oi < 0 and price < 0:
        return "CALL_UNWIND"     # bullish (short covering)
    elif oi < 0 and price > 0:
        return "CALL_SHORT_COVER"
    return "NEUTRAL"


def classify_flow_pe(row):
    oi = row["oi_pe_roll"]
    price = row["price_pe_roll"]

    if oi > 0 and price < 0:
        return "PUT_WRITE"       # bullish support
    elif oi > 0 and price > 0:
        return "PUT_BUY"         # hedging
    elif oi < 0 and price < 0:
        return "PUT_UNWIND"      # bearish
    elif oi < 0 and price > 0:
        return "PUT_SHORT_COVER"
    return "NEUTRAL"

def combined_flow(row):

    ce = row["flow_ce"]
    pe = row["flow_pe"]

    if ce == "CALL_UNWIND" and pe == "PUT_WRITE":
        return "STRONG_BULLISH"

    if ce == "CALL_WRITE" and pe == "PUT_UNWIND":
        return "STRONG_BEARISH"

    if pe == "PUT_WRITE":
        return "BULLISH_BIAS"

    if ce == "CALL_WRITE":
        return "BEARISH_BIAS"

    return "NEUTRAL"


# =========================
# LOAD + FEATURE ENGINEERING
# =========================
@st.cache_data
def load_and_process(file, window):
    df = pd.read_csv(file)
    # Time + sort
    # df["Datetime"] = pd.to_datetime(df["Datetime"])
    df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True) \
                    .dt.tz_convert('Asia/Kolkata') \
                    .dt.tz_localize(None)
    df = df.sort_values(["strike", "Datetime"])

    # =========================
    # DELTA CALCULATIONS
    # =========================
    df["oi_change_CE"] = df.groupby("strike")["OI_CE"].diff()
    df["price_change_CE"] = df.groupby("strike")["Close_CE"].diff()

    df["oi_change_PE"] = df.groupby("strike")["OI_PE"].diff()
    df["price_change_PE"] = df.groupby("strike")["Close_PE"].diff()


    # Fill initial NaN
    df.fillna(0, inplace=True)

    # =========================
    # ROLLING AGGREGATION
    # =========================
    df["oi_ce_roll"] = (
        df.groupby("strike")["oi_change_CE"]
        .rolling(window)
        .sum()
        .reset_index(level=0, drop=True)
    )

    df["price_ce_roll"] = (
        df.groupby("strike")["price_change_CE"]
        .rolling(window)
        .sum()
        .reset_index(level=0, drop=True)
    )

    df["oi_pe_roll"] = (
        df.groupby("strike")["oi_change_PE"]
        .rolling(window)
        .sum()
        .reset_index(level=0, drop=True)
    )

    df["price_pe_roll"] = (
        df.groupby("strike")["price_change_PE"]
        .rolling(window)
        .sum()
        .reset_index(level=0, drop=True)
    )

    df.fillna(0, inplace=True)

    # =========================
    # FLOW CLASSIFICATION
    # =========================
    df["flow_ce"] = df.apply(classify_flow_ce, axis=1)
    df["flow_pe"] = df.apply(classify_flow_pe, axis=1)
    df["combined_flow"] = df.apply(combined_flow, axis=1)

    return df
# =========================
# REGIME DETECTION
# =========================
def flow_bias(row):
    score = 0

    # CALL SIDE
    if row["oi_ce_roll"] < 0 and row['price_ce_roll']<0:
        score += 0   # Call unwinding → booking profit
    elif row["oi_ce_roll"] < 0 and row['price_ce_roll']>0:
        score += 1   # Call writers → covering
    elif row["oi_ce_roll"] > 0 and row["price_ce_roll"] < 0:
        score -= 1   # Call writing → bearish
    elif row["oi_ce_roll"] > 0 and row["price_ce_roll"] > 0:
        score += 1   # Call buying → bullish

    # PUT SIDE
    if row["oi_pe_roll"] < 0 and row['price_pe_roll']<0:
        score += 0   # Put unwinding → booking profits
    elif row["oi_pe_roll"] < 0 and row['price_pe_roll']>0:
        score -= 1   # Put writers → covering
    elif row["oi_pe_roll"] > 0 and row["price_pe_roll"] < 0:
        score += 1   # Put writing → bullish
    elif row["oi_pe_roll"] > 0 and row["price_pe_roll"] > 0:
        score -= 1   # Put buying → bearish

    return score
def classify_regime(row):
    if row["true_bias"] >= 2:
        return "Bullish Support"
    elif row["true_bias"] <= -2:
        return "Bearish Pressure"
    else:
        return "Neutral / Chop"
# ------------------------------------------------------MAIN FUNCTIONS LOADING START---------------------------------------------
df = load_and_process(uploaded_file, window)
with st.expander("Show uploaded"):
    st.dataframe(df)
# =========================
# SIDEBAR SETTING - STRIKE FILTER
# =========================
strikes = sorted(df["strike"].unique())

selected_strikes = st.sidebar.multiselect(
    "Select Strikes",
    strikes,
    default=strikes[:min(1, len(strikes))]
)

df = df[df["strike"].isin(selected_strikes)]


# ---------------ADDED REGIME -----------------------
df['true_bias'] = df.apply(flow_bias,axis=1)
df["regime"] = df.apply(classify_regime, axis=1)

# =========================
# FAKE BREAKOUT
# =========================
df["fake_breakout"] = np.where(
    (abs(df["price_ce_roll"]) + abs(df["price_pe_roll"]) > 50) &
    (abs(df["oi_ce_roll"]) + abs(df["oi_pe_roll"]) < 50000),
    1, 0
)

# =========================
# GAMMA PIN
# =========================
df["distance_from_maxpain"] = abs(df["spot"] - df["max_pain"])
df["pin_strength"] = df["distance_from_maxpain"].rolling(10).mean()
df["gamma_state"] = np.where(df["pin_strength"] < 50, "PINNED", "FREE")

# =========================
# DASHBOARD UI
# =========================
st.subheader("📌 Market Snapshot")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Spot", round(df["spot"].iloc[-1], 2))
col2.metric("Max Pain", round(df["max_pain"].iloc[-1], 2))
col3.metric("Regime", df["regime"].iloc[-1])
col4.metric("Gamma", df["gamma_state"].iloc[-1])

# =========================
# SPOT VS MAX PAIN
# =========================
# fig1 = go.Figure()
# fig1.add_trace(go.Scatter(x=df["Datetime"], y=df["spot"], name="Spot"))
# fig1.add_trace(go.Scatter(x=df["Datetime"], y=df["max_pain"], name="Max Pain"))
# st.plotly_chart(fig1, use_container_width=True)

# ---------------- CHARTS for Selected strikes---------------- #
st.subheader(f"📊 Strike Trend - Historical")

# strike_df_ce = df[(df["strike"] == selected_strikes) & (df["type"] == "CE")].sort_values("Datetime")
# strike_df_pe = hist_df[(df["strike"] == selected_strikes) & (hist_df["type"] == "PE")].sort_values("Datetime")
# if len(strike_df_ce) > 0:
st.write(f"Price Trend for atm strike {selected_strikes}")

fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df["Datetime"], y=df["Close_CE"], name="Price CE"))
fig1.add_trace(go.Scatter(x=df["Datetime"], y=df["Close_PE"], name="Price PE"))
fig1.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]),
                               dict(bounds=[15.5,9.25], pattern="hour")
                              ])
st.plotly_chart(fig1, width='stretch')

st.write(f"OI Trend for atm strike {selected_strikes}")

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df["Datetime"], y=df["OI_CE"], name="OI CE"))
fig2.add_trace(go.Scatter(x=df["Datetime"], y=df["OI_PE"], name="OI PE"))
fig2.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]),
                               dict(bounds=[15.5,9.25], pattern="hour")
                              ])
st.plotly_chart(fig2, width='stretch')

# =========================
# HEATMAP (PUT OI FLOW)
# =========================
# heatmap = df.pivot_table(
#     index="Datetime",
#     columns="strike",
#     values="oi_pe_roll",
#     aggfunc="sum"
# )

# fig2 = px.imshow(heatmap.T, aspect="auto", title="Put OI Heatmap")
# st.plotly_chart(fig2, use_container_width=True)

# =========================
# FLOW TIMELINE
# =========================
fig3 = px.scatter(
    df,
    x="Datetime",
    y="spot",
    color="regime",
    symbol="fake_breakout",
    title="Regime + Fake Breakouts"
)

st.plotly_chart(fig3, use_container_width=True)

# =========================
# FLOW DISTRIBUTION
# =========================
fig4 = px.histogram(df, x="flow_ce", title="Call Flow Distribution")
st.plotly_chart(fig4, use_container_width=True)

fig5 = px.histogram(df, x="flow_pe", title="Put Flow Distribution")
st.plotly_chart(fig5, use_container_width=True)



#=========================
#OC LATEST VIEW
#=========================
# Filter for latest Datetime
st.write(f"Last Updated: {df.Datetime.max().strftime('%Y-%m-%d %H:%M:%S')}")
latest = df[df.Datetime == df.Datetime.max()]
spot = latest["spot"].iloc[0]
max_pain = latest["max_pain"].iloc[0]
chain = latest.sort_values("strike")
chain = chain[["flow_ce","OI_CE","oi_ce_roll","Close_CE","price_ce_roll","strike","flow_pe","Close_PE","price_pe_roll","OI_PE","oi_pe_roll"]]
def highlight_levels(row):
    if row["strike"] == max_pain:
        return ["background-color: purple"] * len(row)
    elif row["strike"] == round(spot/50)*50:
        return ["background-color: yellow"] * len(row)
    return [""] * len(row)

# st.dataframe(chain.style.apply(highlight_levels, axis=1))
with st.expander("Option Chain Details"):
    st.dataframe(chain.style.apply(highlight_levels, axis=1),width=1024, height=768)

# =========================
# REGIME VIEW
# =========================
st.subheader("📄 Regime view - SMART MONEY")
# Identify ATM (nearest strike to spot)>Select range around ATM (e.g. ATM ± 2 strikes)>Use that subset for flow aggregation
# 1. Find Dynamic ATM Strike (per Datetime)
def get_atm(df):
    df["diff"] = (df["strike"] - df["spot"]).abs()
    atm = df.loc[df.groupby("Datetime")["diff"].idxmin(), ["Datetime", "strike"]]
    atm = atm.rename(columns={"strike": "atm_strike"})
    return df.merge(atm, on="Datetime", how="left")
df = get_atm(df)
#Sanity checks ATM Contract
# strike_atm = df[df["strike"] == df["atm_strike"]][["Datetime","strike" ,"OI_PE","oi_change_PE","oi_pe_roll","OI_CE", "oi_change_CE","oi_ce_roll","true_bias","regime"]]  
# with st.expander("Sanity Check for ATM"):
#     st.dataframe(strike_atm,width=1800,height=700)


# 2. Create Dynamic Strike Range (ATM ± N strikes)
# N = 2
#     # Get sorted unique strikes
# strikes = sorted(df["strike"].unique())
#     # Map strike to index
# strike_to_idx = {s: i for i, s in enumerate(strikes)}
# def get_strike_range(row):
#     idx = strike_to_idx[row["atm_strike"]]
#     low = max(0, idx - N)
#     high = min(len(strikes) - 1, idx + N)
#     return strikes[low:high+1]
    # Apply
# df["strike_range"] = df.apply(get_strike_range, axis=1)
# 3. Filter Only Relevant Strikes
# df_filtered = df[df.apply(lambda x: x["strike"] in x["strike_range"], axis=1)]
# with st.expander("Filtered DF based on ATM strikes"):
#     st.dataframe(df_filtered)

# 👉 Aggregate across strikes first:
time_df = df.groupby("Datetime").agg({
    # "spot": "first",
    # "max_pain": "first",
    # "strike_range":"first",
    'OI_CE': "sum",
    'OI_PE': "sum",
    "Close_CE":"sum",
    "Close_PE":"sum",
    "oi_ce_roll": "sum",
    "price_ce_roll":"sum",
    "oi_pe_roll": "sum",
    "price_pe_roll":"sum"
}).reset_index()
time_df['select_pcr'] = time_df["OI_PE"] / time_df["OI_CE"]
time_df['select_straddle']=time_df["Close_CE"]+time_df["Close_PE"]
time_df["flow_ce"] = time_df.apply(classify_flow_ce,axis=1)
time_df["flow_pe"] = time_df.apply(classify_flow_pe,axis=1)
# time_df["net_flow"] = time_df["call_score"] + time_df["put_score"]
time_df["true_bias"] = time_df.apply(flow_bias, axis=1)
time_df["regime"] = time_df.apply(classify_regime, axis=1)
with st.expander("Aggregate strikes across Time"):
    st.dataframe(time_df)

# ---------------- CHARTS for Aggregated data---------------- #
st.subheader(f"📊 ATM Trend - Historical")
st.write(f"Price Trend for ALL ATM strike {selected_strikes}")
fig3 = go.Figure()
fig3.add_trace(go.Scatter(x=time_df["Datetime"], y=time_df["Close_CE"], name="Price CE"))
fig3.add_trace(go.Scatter(x=time_df["Datetime"], y=time_df["Close_PE"], name="Price PE"))
fig3.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]),
                               dict(bounds=[15.5,9.25], pattern="hour")
                              ])
st.plotly_chart(fig3, width='stretch')

st.write(f"OI Trend for all atm strike {selected_strikes}")

fig4 = go.Figure()
fig4.add_trace(go.Scatter(x=time_df["Datetime"], y=time_df["OI_CE"], name="OI CE"))
fig4.add_trace(go.Scatter(x=time_df["Datetime"], y=time_df["OI_PE"], name="OI PE"))
fig4.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]),
                               dict(bounds=[15.5,9.25], pattern="hour")
                              ])
st.plotly_chart(fig4, width='stretch')

fig5 = go.Figure()
fig5.add_trace(go.Scatter(x=time_df["Datetime"], y=time_df["select_pcr"], name="PCR",yaxis="y1"))
fig5.add_trace(go.Scatter(x=time_df["Datetime"], y=time_df["select_straddle"], name="Close",yaxis="y2"))
# Layout with dual axis
fig5.update_layout(
    yaxis=dict(title="PCR"),
    yaxis2=dict(
        title="Straddle Price",
        overlaying="y",
        side="right"
    )
)
fig5.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]),
                               dict(bounds=[15.5,9.25], pattern="hour")
                              ])
st.plotly_chart(fig5, width='stretch')
