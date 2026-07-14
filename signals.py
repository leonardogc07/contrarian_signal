"""
signals.py
----------
Turns raw readings into contrarian "fade the herd" signals, following the
thresholds described in the mosaic guide. These are explicitly heuristic,
not a validated quantitative model - the guide itself says "this isn't a
math formula, it's just part of your mosaic." Treat the composite score as
a qualitative talking point, not a trading trigger.

Signal scale used throughout: -2 (strong bearish / fade bullish herd is wrong
call, be cautious) ... 0 (neutral / no extreme) ... +2 (strong bullish / fade
bearish herd). Positive = contrarian-bullish, negative = contrarian-bearish.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Signal:
    label: str          # human-readable verdict
    score: int           # -2..+2
    detail: str           # short explanation of why


# ---------------------------------------------------------------------------
# Piece 1: AAII Sentiment
# ---------------------------------------------------------------------------

AAII_EXTREME_THRESHOLD = 50.0  # guide: "wait until ~50%+ reading"


def aaii_signal(bullish: float, bearish: float) -> Signal:
    if bullish >= AAII_EXTREME_THRESHOLD:
        return Signal(
            label="Fade the bulls (contrarian bearish)",
            score=-2,
            detail=(
                f"AAII bullish reading is {bullish:.1f}%, at/above the "
                f"{AAII_EXTREME_THRESHOLD:.0f}% extreme. Per the guide, "
                "extremes this large have historically preceded the opposite move."
            ),
        )
    if bearish >= AAII_EXTREME_THRESHOLD:
        return Signal(
            label="Fade the bears (contrarian bullish)",
            score=2,
            detail=(
                f"AAII bearish reading is {bearish:.1f}%, at/above the "
                f"{AAII_EXTREME_THRESHOLD:.0f}% extreme (e.g. late March "
                "2025-style double 50%+ bearish readings marked lows in the guide's example)."
            ),
        )
    spread = bullish - bearish
    return Signal(
        label="No extreme - neutral",
        score=0,
        detail=f"Bullish {bullish:.1f}% / Bearish {bearish:.1f}% (spread {spread:+.1f}pt) - below the extreme threshold.",
    )


# ---------------------------------------------------------------------------
# Piece 2: Put/Call Ratio
# ---------------------------------------------------------------------------

PUTCALL_BEARISH_EXTREME = 0.9   # guide: ">=0.9 probably overly bearish"
PUTCALL_BULLISH_EXTREME = 0.5   # guide: "<=0.5 too optimistic"


def putcall_signal(ratio: float) -> Signal:
    if ratio >= PUTCALL_BEARISH_EXTREME:
        return Signal(
            label="Options crowd overly bearish (contrarian bullish)",
            score=2,
            detail=(
                f"Put/Call ratio {ratio:.2f} is at/above {PUTCALL_BEARISH_EXTREME:.1f} - "
                "more puts being bought relative to calls than usual, suggesting fear/hedging is crowded."
            ),
        )
    if ratio <= PUTCALL_BULLISH_EXTREME:
        return Signal(
            label="Options crowd overly optimistic (contrarian bearish)",
            score=-2,
            detail=(
                f"Put/Call ratio {ratio:.2f} is at/below {PUTCALL_BULLISH_EXTREME:.1f} - "
                "call buying is dominant, suggesting complacency/speculation is crowded."
            ),
        )
    return Signal(
        label="No extreme - neutral",
        score=0,
        detail=f"Put/Call ratio {ratio:.2f} is within the normal {PUTCALL_BULLISH_EXTREME:.1f}-{PUTCALL_BEARISH_EXTREME:.1f} band.",
    )


# ---------------------------------------------------------------------------
# Piece 3: ICI Fund Flows
# ---------------------------------------------------------------------------
# The guide is deliberately qualitative here ("make sure you are not
# outrageously consensus"). We approximate that with a z-score against
# recent history: if this week's flow is a large number of standard
# deviations away from the recent mean, treat it as "outrageously
# consensus" - i.e. everyone moving the same direction at once.

ICI_Z_EXTREME = 2.0


def ici_signal(history: pd.DataFrame, flow_col: str, current_value: Optional[float]) -> Signal:
    if current_value is None:
        return Signal(label="No data", score=0, detail="No current flow figure available.")

    if history is None or history.empty or flow_col not in history.columns or len(history) < 4:
        return Signal(
            label="Insufficient history",
            score=0,
            detail=(
                f"Current {flow_col} flow is {current_value:,.0f}, but not enough "
                "trailing history is cached yet to judge how extreme that is. "
                "Keep fetching weekly to build up context."
            ),
        )

    series = history[flow_col].dropna()
    mean = series.mean()
    std = series.std()
    if std == 0 or pd.isna(std):
        return Signal(label="Insufficient variance", score=0, detail="Not enough variance in cached history to score.")

    z = (current_value - mean) / std

    if z <= -ICI_Z_EXTREME:
        return Signal(
            label="Crowded selling (contrarian bullish on this asset class)",
            score=2,
            detail=(
                f"{flow_col} flow of {current_value:,.0f} is {abs(z):.1f} std devs below "
                "its recent average - a large, one-directional outflow that looks like consensus panic-selling."
            ),
        )
    if z >= ICI_Z_EXTREME:
        return Signal(
            label="Crowded buying (contrarian bearish on this asset class)",
            score=-2,
            detail=(
                f"{flow_col} flow of {current_value:,.0f} is {z:.1f} std devs above "
                "its recent average - a large, one-directional inflow that looks like consensus chasing."
            ),
        )
    return Signal(
        label="Not outrageously consensus",
        score=0,
        detail=f"{flow_col} flow of {current_value:,.0f} is {z:+.1f} std devs from recent average - unremarkable.",
    )


# ---------------------------------------------------------------------------
# Composite mosaic
# ---------------------------------------------------------------------------

def composite_mosaic(signals: list[Signal]) -> str:
    """
    Combines individual piece scores into a plain-English summary. This is
    intentionally not a single number to trade off of - the guide frames
    this as a mosaic you use to "keep a level head," not a signal generator.
    """
    total = sum(s.score for s in signals)
    active = [s for s in signals if s.score != 0]

    if not active:
        return (
            "No sentiment extremes are showing across the pieces you've checked. "
            "That's normal - most of the time nothing is at an extreme, and that's fine. "
            "This mosaic is for spot-checking yourself when YOU feel the urge to buy or sell "
            "something emotionally, not a constant trading signal."
        )

    direction = "leaning contrarian-BULLISH" if total > 0 else "leaning contrarian-BEARISH" if total < 0 else "mixed/conflicting"
    lines = [f"Composite mosaic score: {total:+d} ({direction}).", ""]
    for s in active:
        lines.append(f"- {s.label}: {s.detail}")
    lines.append("")
    lines.append(
        "Reminder from the guide: this is a mosaic to keep you level-headed, not a "
        "formula. Use it to check whether you're 'outrageously consensus' before "
        "acting on an emotional urge to buy or sell - it isn't a standalone signal."
    )
    return "\n".join(lines)
