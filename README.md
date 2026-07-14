# Fading the Masses - Sentiment Mosaic Dashboard

A contrarian sentiment dashboard implementing the "mosaic" framework:

1. **AAII Investor Sentiment Survey** - fade extremes at/above ~50% bullish or bearish.
2. **CBOE Equity Put/Call Ratio** - fade extremes at/above 0.9 (overly bearish options
   positioning) or at/below 0.5 (overly bullish/complacent).
3. **ICI Weekly Fund Flows** - flag when a week's flow is a statistical outlier vs.
   recent history (a proxy for "outrageously consensus" positioning).

The app computes a plain-English **composite mosaic read**, but per the source
guide this is meant to keep you level-headed when you feel an emotional urge
to buy or sell, not to be traded mechanically.

**This is not financial advice.** These are heuristic thresholds from one
specific framework, not a validated quantitative strategy.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (usually `http://localhost:8501`).

## How data gets in

Each of the three panels has a "Fetch latest" button in the sidebar **and**
a manual-entry form. Use manual entry whenever a live fetch fails - and it
will fail sometimes, see below.

## What I tested vs. what you need to verify

I built and ran this in a sandboxed environment **with no internet access**,
so I could not run the scrapers against the live websites. Here's exactly
what was and wasn't verified before handing this to you:

| Component | What I verified | What you need to check |
|---|---|---|
| `signals.py` (all threshold logic, z-scores, composite scoring) | Ran real unit tests with synthetic data confirming the 50% AAII rule, 0.9/0.5 put-call rule, and z-score ICI logic all fire correctly | Nothing - this part is pure Python, no network dependency |
| AAII table parser | Ran against a mock HTML table shaped like AAII's real table (Date/Bullish/Neutral/Bearish columns) and confirmed correct extraction | Run `fetch_aaii_sentiment()` live once and confirm it grabs the current week - aaii.com occasionally reshuffles page layout |
| Put/Call scraper (ycharts) | Not testable offline; also flagged as unreliable by design (JS-rendered value, vendor ToS concerns) | Don't rely on this one - it's included for completeness only |
| Put/Call scraper (CBOE) | Not testable offline | Run it live; CBOE has changed this page's URL/format more than once historically, so you may need to update `candidate_urls` in `data_sources.py` |
| ICI flows scraper | Not testable offline | Run it live; if the linked spreadsheet's column layout doesn't match, use manual entry with figures read off ici.org |
| Streamlit UI (`app.py`) | Syntax-checked, and manually traced through the data flow (fetch → session_state → cache → signal → display) | Run `streamlit run app.py` locally and click through the buttons/forms once - I could not launch a real Streamlit server in this sandbox |

**Bottom line:** the "brain" of the app (the contrarian logic) is genuinely
tested and correct. The "hands" of the app (the three scrapers) are written
defensively with real fallbacks, but websites change, so expect to spend a
few minutes on your first live run confirming each one still finds the
right table/link, and lean on manual entry immediately if one breaks.

## A note on the put/call ratio source

ycharts.com is a paid commercial data vendor. Scraping their page directly is
unreliable (the number is often rendered via JavaScript, so a plain HTTP
request won't see it) and may run against their Terms of Service. This app
defaults to pulling the same underlying data straight from CBOE, which
publishes it for free. If CBOE's page structure has moved again by the time
you run this, use manual entry - it takes 10 seconds to read the ratio off
their site yourself.

## Files

- `app.py` - Streamlit UI, entry point
- `data_sources.py` - scrapers + manual-entry-friendly data classes + local CSV caching
- `signals.py` - all contrarian threshold/scoring logic
- `data/` - auto-created local CSV cache of everything you fetch or enter (builds history over time)
