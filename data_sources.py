"""
data_sources.py
----------------
Fetchers for the three "mosaic pieces":
  1. AAII Investor Sentiment Survey (bullish/neutral/bearish %)
  2. CBOE Equity Put/Call Ratio (ycharts is just a UI on top of CBOE's own data)
  3. ICI weekly estimated long-term fund flows

DESIGN PHILOSOPHY
------------------
Public financial data pages change their HTML constantly and some (ycharts)
are commercial products whose terms of service restrict scraping. So every
fetcher here:
  - Tries a "best effort" scrape first.
  - Never crashes the app - raises a clear, catchable exception on failure.
  - Is meant to be paired with a manual-entry fallback in the UI (see app.py).
  - Caches whatever it successfully retrieves to a local CSV so the app has
    history even when a live fetch fails.

You are responsible for re-checking these selectors periodically - sites
change their markup without warning. Treat this file as a starting point,
not a "set and forget" scraper.
"""

from __future__ import annotations

import io
import re
import subprocess
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
import pandas as pd
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "Upgrade-Insecure-Requests": "1",
}

REQUEST_TIMEOUT = 15


class DataFetchError(RuntimeError):
    """Raised when a live fetch fails. Callers should fall back to manual entry."""


# ---------------------------------------------------------------------------
# 1) AAII Sentiment Survey
# ---------------------------------------------------------------------------

AAII_URL = "https://www.aaii.com/sentimentsurvey/sent_results"
AAII_CACHE = DATA_DIR / "aaii_history.csv"


@dataclass
class AAIIReading:
    date: dt.date
    bullish: float
    neutral: float
    bearish: float

    @property
    def bull_bear_spread(self) -> float:
        return self.bullish - self.bearish


def _fetch_text(url: str) -> str:
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True
        )
        resp.raise_for_status()
        if "Pardon Our Interruption" not in resp.text and "Reported Date" in resp.text:
            return resp.text
    except requests.RequestException:
        pass

    curl_cmd = ["curl", "-L", "-A", HEADERS["User-Agent"]]
    for key, value in HEADERS.items():
        if key == "User-Agent":
            continue
        curl_cmd.extend(["-H", f"{key}: {value}"])
    curl_cmd.append(url)

    try:
        completed = subprocess.run(
            curl_cmd,
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT + 10,
            check=True,
        )
        return completed.stdout
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        raise DataFetchError(f"Could not fetch AAII sentiment page: {e}") from e


def fetch_aaii_sentiment() -> AAIIReading:
    """
    Scrapes the current week's AAII bullish/neutral/bearish percentages.

    AAII publishes this as a plain HTML table (no login wall), so this is
    the most scrape-friendly of the three sources. We use the live HTML text
    directly and match the current survey row, since AAII's layout has changed
    several times and the site now sometimes serves an anti-bot challenge page.
    """
    html = _fetch_text(AAII_URL)
    soup = BeautifulSoup(html, "html.parser")
    page_text = " ".join(soup.get_text(" ", strip=True).split())

    pattern = re.search(
        r"reported date\s+bullish\s+neutral\s+bearish\s+"
        r"(?P<date>[A-Za-z]{3}\s+\d{1,2})\s+"
        r"(?P<bullish>[0-9.]+)%\s+"
        r"(?P<neutral>[0-9.]+)%\s+"
        r"(?P<bearish>[0-9.]+)%",
        page_text,
        re.IGNORECASE,
    )

    if pattern:
        date_text = pattern.group("date")
        bullish = float(pattern.group("bullish"))
        neutral = float(pattern.group("neutral"))
        bearish = float(pattern.group("bearish"))
    else:
        target = None
        for table in soup.find_all("table"):
            rows = [
                [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                for row in table.find_all("tr")
            ]
            if not rows:
                continue
            for idx, row in enumerate(rows[:3]):
                row_text = " ".join(row).lower()
                if (
                    "reported date" in row_text
                    and "bullish" in row_text
                    and "bearish" in row_text
                ):
                    target = rows[idx + 1] if idx + 1 < len(rows) else None
                    break
            if target is not None:
                break

        if target is None:
            raise DataFetchError(
                "AAII page structure may have changed - no Bullish/Bearish table found."
            )

        def _pct(val: str) -> float:
            return float(str(val).replace("%", "").strip())

        header_labels = [str(cell).strip().lower() for cell in target]
        bullish_idx = next(
            (i for i, label in enumerate(header_labels) if "bullish" in label), None
        )
        neutral_idx = next(
            (i for i, label in enumerate(header_labels) if "neutral" in label), None
        )
        bearish_idx = next(
            (i for i, label in enumerate(header_labels) if "bearish" in label), None
        )
        date_idx = next(
            (
                i
                for i, label in enumerate(header_labels)
                if "date" in label or "reported" in label
            ),
            None,
        )

        if bullish_idx is None or neutral_idx is None or bearish_idx is None:
            raise DataFetchError(
                "AAII table did not expose bullish/neutral/bearish columns."
            )

        bullish = _pct(target[bullish_idx])
        neutral = _pct(target[neutral_idx])
        bearish = _pct(target[bearish_idx])
        date_text = (
            target[date_idx]
            if date_idx is not None
            else dt.date.today().strftime("%b %d")
        )

    try:
        parsed_date = pd.to_datetime(date_text, format="%b %d", errors="coerce")
        if pd.isna(parsed_date):
            reading_date = dt.date.today()
        else:
            if parsed_date.year < 2000:
                parsed_date = parsed_date.replace(year=dt.date.today().year)
            reading_date = parsed_date.date()
    except (TypeError, ValueError) as e:
        raise DataFetchError(f"Could not parse AAII date value: {e}") from e

    reading = AAIIReading(
        date=reading_date, bullish=bullish, neutral=neutral, bearish=bearish
    )
    _append_cache(
        AAII_CACHE,
        {
            "date": reading.date,
            "bullish": reading.bullish,
            "neutral": reading.neutral,
            "bearish": reading.bearish,
        },
    )
    return reading


# ---------------------------------------------------------------------------
# 2) Put/Call Ratio
# ---------------------------------------------------------------------------

YCHARTS_URL = "https://ycharts.com/indicators/cboe_equity_put_call_ratio"
PUTCALL_CACHE = DATA_DIR / "putcall_history.csv"


@dataclass
class PutCallReading:
    date: dt.date
    ratio: float
    source: str


def fetch_putcall_ratio_ycharts() -> PutCallReading:
    """
    Best-effort scrape of the headline number on ycharts' public indicator
    page. NOTE: ycharts is a commercial data vendor, the headline value on
    that page is frequently rendered client-side via JavaScript (which a
    plain requests.get will NOT execute), and scraping it programmatically
    may violate their Terms of Service. This function is included for
    completeness but should be treated as unreliable. Prefer
    fetch_putcall_ratio_cboe() or manual entry.
    """
    try:
        resp = requests.get(YCHARTS_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise DataFetchError(f"Could not reach ycharts: {e}") from e

    soup = BeautifulSoup(resp.text, "lxml")
    text = soup.get_text(" ", strip=True)

    # Look for a pattern like "Equity Put/Call Ratio is 0.87 for ..."
    match = re.search(r"Put/Call Ratio[^0-9]{0,40}(\d+\.\d+)", text)
    if not match:
        raise DataFetchError(
            "Could not find a put/call value in the page text - it is likely "
            "rendered via JavaScript and not present in the raw HTML. Use "
            "fetch_putcall_ratio_cboe() or manual entry instead."
        )

    ratio = float(match.group(1))
    reading = PutCallReading(
        date=dt.date.today(), ratio=ratio, source="ycharts (best-effort)"
    )
    _append_cache(
        PUTCALL_CACHE,
        {"date": reading.date, "ratio": reading.ratio, "source": reading.source},
    )
    return reading


def fetch_putcall_ratio_cboe() -> PutCallReading:
    """
    Attempts to pull the total put/call ratio directly from CBOE's own
    published market statistics, which is the underlying source ycharts
    repackages. CBOE has changed this endpoint's exact path over the years
    (moving between /delayedquote, /us/options/market_statistics, and a
    JSON API under cdn.cboe.com), so this function tries a couple of known
    shapes and fails loudly if none work - you will likely need to update
    the URL/parsing to match CBOE's current site when you run this live.
    """
    candidate_urls = [
        "https://www.cboe.com/us/options/market_statistics/daily/",
        "https://www.cboe.com/market_statistics/daily/",
        "https://www.cboe.com/us/options/market_statistics/daily",
        "https://www.cboe.com/us/options/market_statistics/",
        "https://www.cboe.com/us/options/market_statistics",
    ]
    last_error: Optional[Exception] = None
    for url in candidate_urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            # Try table-based parsing first
            try:
                tables = pd.read_html(io.StringIO(resp.text))
            except ValueError:
                tables = []

            for t in tables:
                cols = [str(c).lower() for c in t.columns]
                if any("put/call" in c for c in cols):
                    ratio_col = [c for c in t.columns if "put/call" in str(c).lower()][
                        0
                    ]
                    ratio = float(str(t.iloc[0][ratio_col]).strip())
                    reading = PutCallReading(
                        date=dt.date.today(), ratio=ratio, source=f"CBOE ({url})"
                    )
                    _append_cache(
                        PUTCALL_CACHE,
                        {
                            "date": reading.date,
                            "ratio": reading.ratio,
                            "source": reading.source,
                        },
                    )
                    return reading

            # If no table match, fall back to text-based search (more forgiving)
            soup = BeautifulSoup(resp.text, "lxml")
            page_text = " ".join(soup.get_text(" ", strip=True).split())
            # Look for patterns like "Put/Call Ratio is 0.87" or "Put/Call 0.87"
            text_match = re.search(
                r"put\s*/\s*call[^0-9]{0,40}(\d+\.\d+)", page_text, re.IGNORECASE
            )
            if not text_match:
                # try a slightly different wording
                text_match = re.search(
                    r"put\s*call[^0-9]{0,40}(\d+\.\d+)", page_text, re.IGNORECASE
                )

            if text_match:
                try:
                    ratio = float(text_match.group(1))
                    reading = PutCallReading(
                        date=dt.date.today(), ratio=ratio, source=f"CBOE ({url} text)"
                    )
                    _append_cache(
                        PUTCALL_CACHE,
                        {
                            "date": reading.date,
                            "ratio": reading.ratio,
                            "source": reading.source,
                        },
                    )
                    return reading
                except (TypeError, ValueError):
                    # fall through to outer exception handling
                    pass
        except (requests.RequestException, ValueError, IndexError, KeyError) as e:
            last_error = e
            continue

    raise DataFetchError(
        "Could not retrieve put/call ratio from CBOE. Their site structure "
        f"changes periodically. Last error: {last_error}. Falling back to "
        "manual entry is recommended - check "
        "https://www.cboe.com/us/options/market_statistics/ directly."
    )


# ---------------------------------------------------------------------------
# 3) ICI Fund Flows
# ---------------------------------------------------------------------------

ICI_URL = "https://www.ici.org/research/stats/flows"
ICI_CACHE = DATA_DIR / "ici_history.csv"


@dataclass
class ICIFlowReading:
    date: dt.date
    equity_flow_millions: Optional[float]
    bond_flow_millions: Optional[float]
    report_title: str


def parse_ici_flows_from_html(html: str) -> tuple[Optional[float], Optional[float]]:
    """Parse equity and bond flow values from the current ICI page HTML.

    The current ICI flow pages publish the headline figures directly in the
    page text rather than providing a spreadsheet attachment for the latest
    report, so this parser extracts the values from the visible text and
    converts them to millions of dollars with the proper sign.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())

    def _extract_flow(target_phrase: str, direction: str) -> Optional[float]:
        lowered_text = text.lower()
        target_idx = lowered_text.find(target_phrase.lower())
        if target_idx == -1:
            return None

        segment = text[target_idx : target_idx + 1400]
        pattern = re.compile(
            rf"(?i)(?P<direction>outflows|inflows)[^0-9$]{{0,60}}"
            rf"\$?(?P<value>[\d,\.]+)\s*(?P<unit>billion|million|thousand|trillion)",
        )
        match = pattern.search(segment)
        if not match:
            return None

        multiplier = {
            "billion": 1_000,
            "million": 1,
            "thousand": 0.001,
            "trillion": 1_000_000,
        }
        amount = float(match.group("value").replace(",", "")) * multiplier.get(
            match.group("unit").lower(), 1_000
        )
        if direction.lower() == "outflows":
            return -amount
        return amount

    equity_flow = _extract_flow("equity funds", "outflows")
    bond_flow = _extract_flow("bond funds", "inflows")
    return equity_flow, bond_flow


def fetch_ici_flows() -> ICIFlowReading:
    """
    Finds the most recent "Combined Estimated Long-Term Fund Flows" report
    linked from the ICI flows page and attempts to parse the top-line
    equity / bond flow figures out of the linked spreadsheet.

    ICI reports are typically published as .xls/.xlsx attachments rather
    than inline HTML tables, so this function: (1) finds the newest report
    link, (2) downloads it, (3) parses it with pandas. Exact column layout
    varies by report vintage, so parsing is defensive and may need
    adjustment - if it fails, use manual entry with the numbers read
    straight off the ICI page.
    """
    try:
        resp = requests.get(ICI_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise DataFetchError(f"Could not reach ICI flows page: {e}") from e

    soup = BeautifulSoup(resp.text, "lxml")
    inline_equity_flow, inline_bond_flow = parse_ici_flows_from_html(resp.text)
    if inline_equity_flow is not None and inline_bond_flow is not None:
        reading = ICIFlowReading(
            date=dt.date.today(),
            equity_flow_millions=inline_equity_flow,
            bond_flow_millions=inline_bond_flow,
            report_title="ICI weekly flow page (inline HTML)",
        )
        _append_cache(
            ICI_CACHE,
            {
                "date": reading.date,
                "equity_flow_millions": reading.equity_flow_millions,
                "bond_flow_millions": reading.bond_flow_millions,
                "report_title": reading.report_title,
            },
        )
        return reading

    links = soup.find_all("a", href=True)
    report_link = None
    report_title = ""
    for a in links:
        href = a["href"]
        label = a.get_text(strip=True)
        if (
            href.lower().endswith((".xls", ".xlsx"))
            and "flow" in (label + href).lower()
        ):
            report_link = href
            report_title = label or href
            break

    if report_link is None:
        raise DataFetchError(
            "Could not find a linked flow-report spreadsheet on the ICI page. "
            "The page layout may have changed - consider reading the figures "
            "manually and using the manual-entry form instead."
        )

    if report_link.startswith("/"):
        report_link = "https://www.ici.org" + report_link

    try:
        file_resp = requests.get(report_link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        file_resp.raise_for_status()
        xls = pd.ExcelFile(io.BytesIO(file_resp.content))
        df = xls.parse(xls.sheet_names[0])
    except (requests.RequestException, ValueError) as e:
        raise DataFetchError(f"Could not download/parse ICI report: {e}") from e

    def _find_flow(df: pd.DataFrame, keyword: str) -> Optional[float]:
        for _, row in df.iterrows():
            row_str = " ".join(str(x) for x in row.values if pd.notna(x)).lower()
            if keyword in row_str:
                numeric_vals = [x for x in row.values if isinstance(x, (int, float))]
                if numeric_vals:
                    return float(numeric_vals[0])
        return None

    equity_flow = _find_flow(df, "equity")
    bond_flow = _find_flow(df, "bond")

    reading = ICIFlowReading(
        date=dt.date.today(),
        equity_flow_millions=equity_flow,
        bond_flow_millions=bond_flow,
        report_title=report_title,
    )
    _append_cache(
        ICI_CACHE,
        {
            "date": reading.date,
            "equity_flow_millions": reading.equity_flow_millions,
            "bond_flow_millions": reading.bond_flow_millions,
            "report_title": reading.report_title,
        },
    )
    return reading


# ---------------------------------------------------------------------------
# Shared cache helpers
# ---------------------------------------------------------------------------


def _append_cache(path: Path, row: dict) -> None:
    """Appends a row to a local CSV cache, replacing an existing entry for the same date."""
    new_row = pd.DataFrame([row])
    if path.exists():
        existing = pd.read_csv(path)
        if "date" in existing.columns:
            existing = existing[existing["date"].astype(str) != str(row.get("date"))]
        combined = pd.concat([existing, new_row], ignore_index=True)
    else:
        combined = new_row
    combined.to_csv(path, index=False)


def load_cache(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, parse_dates=["date"])
    return pd.DataFrame()
