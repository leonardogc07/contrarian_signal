"""
Fading the Masses - Sentiment Mosaic Dashboard
================================================
Run with:  streamlit run app.py

A contrarian sentiment "mosaic" dashboard combining:
  1. AAII Investor Sentiment Survey
  2. CBOE Equity Put/Call Ratio
  3. ICI Weekly Fund Flows

IMPORTANT: This tool is for informational/research purposes only and is
not financial advice. Thresholds are heuristics from a specific mosaic
framework, not a validated quantitative strategy. Live web scraping can
break whenever a source site changes its layout - manual entry is always
available as a fallback so the app keeps working even when a scraper doesn't.
"""

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_sources as ds
import signals as sig

st.set_page_config(page_title="Fading the Masses - Sentiment Mosaic", layout="wide")

st.title("Fading the Masses - Sentiment Mosaic Dashboard")
st.caption(
    "A contrarian mosaic combining AAII sentiment, put/call ratio, and ICI fund flows. "
    "Not financial advice - this quantifies a qualitative framework, it doesn't replace judgment."
)

# ---------------------------------------------------------------------------
# Sidebar: data controls
# ---------------------------------------------------------------------------
st.sidebar.header("Data Controls")
st.sidebar.markdown(
    "Live scraping can fail if a source site changes its layout, blocks bots, "
    "or renders values via JavaScript. If a fetch fails, use manual entry below."
)

if st.sidebar.button("Fetch latest AAII data"):
    try:
        r = ds.fetch_aaii_sentiment()
        st.session_state["aaii"] = r
        st.sidebar.success(f"AAII updated: {r.date}")
    except ds.DataFetchError as e:
        st.sidebar.error(f"AAII fetch failed: {e}")

if st.sidebar.button("Fetch latest Put/Call (CBOE)"):
    try:
        r = ds.fetch_putcall_ratio_cboe()
        st.session_state["putcall"] = r
        st.sidebar.success(f"Put/Call updated: {r.ratio:.2f}")
    except ds.DataFetchError as e:
        st.sidebar.error(f"Put/Call fetch failed: {e}")

if st.sidebar.button("Fetch latest ICI flows"):
    try:
        r = ds.fetch_ici_flows()
        st.session_state["ici"] = r
        st.sidebar.success(f"ICI updated: {r.date}")
    except ds.DataFetchError as e:
        st.sidebar.error(f"ICI fetch failed: {e}")

st.sidebar.divider()
st.sidebar.subheader("Manual entry (fallback)")
st.sidebar.caption("Use these if a live fetch above fails or you're reading the numbers off the source site yourself.")

with st.sidebar.form("manual_aaii"):
    st.markdown("**AAII**")
    m_bull = st.number_input("Bullish %", 0.0, 100.0, 35.0)
    m_bear = st.number_input("Bearish %", 0.0, 100.0, 35.0)
    if st.form_submit_button("Save AAII manual entry"):
        st.session_state["aaii"] = ds.AAIIReading(
            date=dt.date.today(), bullish=m_bull, neutral=max(0.0, 100 - m_bull - m_bear), bearish=m_bear
        )
        ds._append_cache(ds.AAII_CACHE, {
            "date": dt.date.today(), "bullish": m_bull,
            "neutral": max(0.0, 100 - m_bull - m_bear), "bearish": m_bear,
        })

with st.sidebar.form("manual_putcall"):
    st.markdown("**Put/Call Ratio**")
    m_ratio = st.number_input("Ratio", 0.0, 3.0, 0.7, step=0.01)
    if st.form_submit_button("Save Put/Call manual entry"):
        st.session_state["putcall"] = ds.PutCallReading(date=dt.date.today(), ratio=m_ratio, source="manual")
        ds._append_cache(ds.PUTCALL_CACHE, {"date": dt.date.today(), "ratio": m_ratio, "source": "manual"})

with st.sidebar.form("manual_ici"):
    st.markdown("**ICI Flows (millions $)**")
    m_equity = st.number_input("Equity flow", value=0.0, step=100.0)
    m_bond = st.number_input("Bond flow", value=0.0, step=100.0)
    if st.form_submit_button("Save ICI manual entry"):
        st.session_state["ici"] = ds.ICIFlowReading(
            date=dt.date.today(), equity_flow_millions=m_equity,
            bond_flow_millions=m_bond, report_title="manual entry",
        )
        ds._append_cache(ds.ICI_CACHE, {
            "date": dt.date.today(), "equity_flow_millions": m_equity,
            "bond_flow_millions": m_bond, "report_title": "manual entry",
        })

# ---------------------------------------------------------------------------
# Load cached history
# ---------------------------------------------------------------------------
aaii_hist = ds.load_cache(ds.AAII_CACHE)
putcall_hist = ds.load_cache(ds.PUTCALL_CACHE)
ici_hist = ds.load_cache(ds.ICI_CACHE)

aaii_reading = st.session_state.get("aaii")
putcall_reading = st.session_state.get("putcall")
ici_reading = st.session_state.get("ici")

if aaii_reading is None and not aaii_hist.empty:
    last = aaii_hist.iloc[-1]
    aaii_reading = ds.AAIIReading(date=last["date"], bullish=last["bullish"], neutral=last["neutral"], bearish=last["bearish"])
if putcall_reading is None and not putcall_hist.empty:
    last = putcall_hist.iloc[-1]
    putcall_reading = ds.PutCallReading(date=last["date"], ratio=last["ratio"], source=last.get("source", "cache"))
if ici_reading is None and not ici_hist.empty:
    last = ici_hist.iloc[-1]
    ici_reading = ds.ICIFlowReading(
        date=last["date"],
        equity_flow_millions=last.get("equity_flow_millions"),
        bond_flow_millions=last.get("bond_flow_millions"),
        report_title=last.get("report_title", "cache"),
    )

# ---------------------------------------------------------------------------
# Main dashboard: three mosaic pieces
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)


def gauge(value: float, title: str, min_v: float, max_v: float, band_low: float, band_high: float) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title},
        gauge={
            "axis": {"range": [min_v, max_v]},
            "bar": {"color": "#2c3e50"},
            "steps": [
                {"range": [min_v, band_low], "color": "#dfe9f5"},
                {"range": [band_low, band_high], "color": "#f5f0df"},
                {"range": [band_high, max_v], "color": "#dfe9f5"},
            ],
        },
    ))
    fig.update_layout(height=220, margin=dict(l=20, r=20, t=40, b=10))
    return fig


with col1:
    st.subheader("Piece 1: AAII Sentiment")
    if aaii_reading:
        st.plotly_chart(
            gauge(aaii_reading.bullish, "Bullish %", 0, 100, 0, sig.AAII_EXTREME_THRESHOLD),
            use_container_width=True,
        )
        s1 = sig.aaii_signal(aaii_reading.bullish, aaii_reading.bearish)
        st.metric("Bullish", f"{aaii_reading.bullish:.1f}%")
        st.metric("Bearish", f"{aaii_reading.bearish:.1f}%")
        st.info(f"**{s1.label}**\n\n{s1.detail}")
        if not aaii_hist.empty:
            st.line_chart(aaii_hist.set_index("date")[["bullish", "bearish"]])
    else:
        s1 = sig.Signal("No data", 0, "Fetch or manually enter AAII data.")
        st.warning("No AAII data yet - fetch live or enter manually in the sidebar.")

with col2:
    st.subheader("Piece 2: Put/Call Ratio")
    if putcall_reading:
        st.plotly_chart(
            gauge(putcall_reading.ratio, "Put/Call Ratio", 0, 1.5,
                  sig.PUTCALL_BULLISH_EXTREME, sig.PUTCALL_BEARISH_EXTREME),
            use_container_width=True,
        )
        s2 = sig.putcall_signal(putcall_reading.ratio)
        st.metric("Ratio", f"{putcall_reading.ratio:.2f}", help=f"Source: {putcall_reading.source}")
        st.info(f"**{s2.label}**\n\n{s2.detail}")
        if not putcall_hist.empty:
            st.line_chart(putcall_hist.set_index("date")[["ratio"]])
    else:
        s2 = sig.Signal("No data", 0, "Fetch or manually enter put/call data.")
        st.warning("No put/call data yet - fetch live or enter manually in the sidebar.")

with col3:
    st.subheader("Piece 3: ICI Fund Flows")
    if ici_reading:
        st.metric("Equity flow ($M)", f"{ici_reading.equity_flow_millions:,.0f}" if ici_reading.equity_flow_millions is not None else "N/A")
        st.metric("Bond flow ($M)", f"{ici_reading.bond_flow_millions:,.0f}" if ici_reading.bond_flow_millions is not None else "N/A")
        s3_equity = sig.ici_signal(ici_hist, "equity_flow_millions", ici_reading.equity_flow_millions)
        s3_bond = sig.ici_signal(ici_hist, "bond_flow_millions", ici_reading.bond_flow_millions)
        st.info(f"**Equity: {s3_equity.label}**\n\n{s3_equity.detail}")
        st.info(f"**Bond: {s3_bond.label}**\n\n{s3_bond.detail}")
        if not ici_hist.empty:
            st.line_chart(ici_hist.set_index("date")[["equity_flow_millions", "bond_flow_millions"]])
    else:
        s3_equity = sig.Signal("No data", 0, "Fetch or manually enter ICI data.")
        s3_bond = sig.Signal("No data", 0, "Fetch or manually enter ICI data.")
        st.warning("No ICI flow data yet - fetch live or enter manually in the sidebar.")

st.divider()
st.subheader("Composite Mosaic Read")
st.text(sig.composite_mosaic([s1, s2, s3_equity, s3_bond]))

st.divider()
with st.expander("About this tool / limitations"):
    st.markdown(
        """
- **Not financial advice.** This encodes one specific contrarian heuristic framework; it is one input among many, not a signal generator.
- **AAII** data comes from a public HTML table on aaii.com and is the most scrape-reliable of the three sources.
- **Put/Call ratio**: ycharts.com is a paid vendor and often renders values via JavaScript, so scraping it directly is unreliable and may violate their terms. This app defaults to CBOE's own published statistics, with manual entry as a fallback.
- **ICI fund flows** are published as downloadable spreadsheets that occasionally change format between reports - if parsing fails, read the current week's figures off ici.org and enter them manually.
- Thresholds (AAII 50%, put/call 0.9 / 0.5, ICI z-score of 2) are the heuristics described in the source guide, not statistically validated cutoffs. Treat the "composite mosaic" number as a talking point for checking your own emotional bias, not a trade trigger.
        """
    )
