"""Run TradingAgents for one ticker and write the decision to a markdown file.

Reads:
  TICKER          - ticker symbol (e.g. NVDA)
  OPENAI_API_KEY  - OpenAI API key
  OUTPUT_FILE     - path for markdown output (default: decision.md)

Exit codes:
  0 - success, markdown written
  1 - failure, markdown still written with error details so the issue is created
"""

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Plain-English summary uses a cheap model. Bumping max chars trims long
# inputs to keep the summarizer call fast and within reasonable cost.
SUMMARY_MODEL = "gpt-5.4-mini"
SUMMARY_INPUT_CHAR_LIMIT = 12_000
# GitHub issue body limit is 65,536; leave headroom for headers/markdown.
ISSUE_BODY_CHAR_LIMIT = 60_000

RATING_SCALE_TABLE = """_Starting position: $5K per ticker. Adjust per the rule below. Caps: 20% per ticker, 80% total exposure._

| Rating | What it means | My action |
|---|---|---|
| **Buy** | Strong conviction — significantly bullish | **Add $2K worth** |
| **Overweight** | Moderately bullish | **Add $1K worth** |
| **Hold** | No edge either direction | **Do nothing** |
| **Underweight** | Moderately bearish | **Sell $1K worth** |
| **Sell** | Strong conviction — significantly bearish | **Sell $2K worth** |
"""

PLAIN_ENGLISH_PROMPT = """You're explaining a stock analysis to a friend who is interested in investing
but is NOT a finance expert. They don't know what RSI, MACD, EMA, or P/E ratio mean.

Given the Portfolio Manager's decision below, produce TWO things:

1. A "What this means" section: 2-3 sentences in plain English explaining the
   recommendation and what action they would take. No finance jargon. If you
   absolutely must use a term, briefly explain it in parentheses.

2. A "Why" section: 3-5 short bullet points (one sentence each) covering the
   main reasons. Plain English, conversational tone.

Output format (use this exactly):

## What this means

<your 2-3 sentences>

**Why:**
- <bullet 1>
- <bullet 2>
- <bullet 3>

Now here is the decision to summarize:

TICKER: {ticker}
RATING: {rating}

PORTFOLIO MANAGER NARRATIVE:
{narrative}
"""


def truncate(text: str, limit: int) -> str:
    if not text or len(text) <= limit:
        return text or ""
    return text[:limit] + f"\n\n_[truncated — {len(text) - limit} more chars]_"


def generate_plain_summary(ticker: str, rating: str, narrative: str) -> str:
    """One cheap LLM call to translate the PM decision into plain English."""
    try:
        from openai import OpenAI

        prompt = PLAIN_ENGLISH_PROMPT.format(
            ticker=ticker,
            rating=rating,
            narrative=truncate(narrative, SUMMARY_INPUT_CHAR_LIMIT),
        )
        client = OpenAI()
        resp = client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        return f"_(plain-English summary failed: {exc})_"


def section(title: str, body: str) -> str:
    """A collapsible <details> block. GitHub renders these natively."""
    body = (body or "_(empty)_").strip()
    return f"<details>\n<summary><b>{title}</b></summary>\n\n{body}\n\n</details>\n"


def render_decision(
    ticker: str, date: str, rating, final_state: dict, plain_summary: str
) -> str:
    final_state = final_state or {}
    rating_str = rating if isinstance(rating, str) else str(rating)
    generated_at = datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")

    pm_narrative = final_state.get("final_trade_decision", "_(no narrative returned)_")
    trader_plan = final_state.get("trader_investment_plan", "")
    invest_debate = final_state.get("investment_debate_state", {}) or {}
    risk_debate = final_state.get("risk_debate_state", {}) or {}

    bull_bear_section = (
        f"### Research Manager's call\n\n{invest_debate.get('judge_decision', '_(none)_')}\n\n"
        f"### Bull case\n\n{invest_debate.get('bull_history', '_(none)_')}\n\n"
        f"### Bear case\n\n{invest_debate.get('bear_history', '_(none)_')}"
    )

    risk_section = (
        f"### Risk Manager's call\n\n{risk_debate.get('judge_decision', '_(none)_')}\n\n"
        f"### Aggressive view\n\n{risk_debate.get('aggressive_history', '_(none)_')}\n\n"
        f"### Conservative view\n\n{risk_debate.get('conservative_history', '_(none)_')}\n\n"
        f"### Neutral view\n\n{risk_debate.get('neutral_history', '_(none)_')}"
    )

    analyst_section = (
        f"### Technical (price/chart) analyst\n\n{final_state.get('market_report', '_(none)_')}\n\n"
        f"### Sentiment analyst\n\n{final_state.get('sentiment_report', '_(none)_')}\n\n"
        f"### News analyst\n\n{final_state.get('news_report', '_(none)_')}\n\n"
        f"### Fundamentals analyst\n\n{final_state.get('fundamentals_report', '_(none)_')}"
    )

    body = (
        f"# {ticker} — {date} — {rating_str}\n\n"
        f"_Generated {generated_at} (NY)_\n\n"
        f"### 📖 Rating scale\n\n"
        f"{RATING_SCALE_TABLE}\n"
        f"---\n\n"
        f"{plain_summary}\n\n"
        f"---\n\n"
        f"{section('📋 Portfolio Manager Decision (the official call)', pm_narrative)}\n"
        f"{section('🤖 Trader’s plan', trader_plan)}\n"
        f"{section('⚖️ Bull vs Bear debate', bull_bear_section)}\n"
        f"{section('🛡️ Risk team discussion', risk_section)}\n"
        f"{section('📊 Full analyst reports', analyst_section)}\n"
    )
    return truncate(body, ISSUE_BODY_CHAR_LIMIT)


def render_error(ticker: str, date: str, exc: BaseException) -> str:
    return (
        f"# {ticker} — {date} (FAILED)\n\n"
        f"_Generated {datetime.now(ZoneInfo('America/New_York')).isoformat(timespec='seconds')} (NY)_\n\n"
        "## Error\n\n"
        f"```\n{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}\n```\n"
    )


def main() -> int:
    ticker = os.environ["TICKER"].strip().upper()
    output_file = Path(os.environ.get("OUTPUT_FILE", "decision.md"))
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "openai"
        config["deep_think_llm"] = "gpt-5.4"
        config["quick_think_llm"] = "gpt-5.4-mini"
        config["max_debate_rounds"] = 1
        config["online_tools"] = True

        ta = TradingAgentsGraph(debug=False, config=config)
        final_state, decision = ta.propagate(ticker, today)

        narrative = (final_state or {}).get("final_trade_decision", "")
        plain_summary = generate_plain_summary(ticker, str(decision), narrative)

        output_file.write_text(
            render_decision(ticker, today, decision, final_state, plain_summary)
        )
        # Write the bare rating to a sidecar file so the trade-execution
        # step can read it without re-parsing the markdown.
        Path(os.environ.get("RATING_FILE", "rating.txt")).write_text(str(decision).strip())
        print(f"Wrote decision for {ticker} to {output_file}")
        return 0
    except Exception as exc:
        output_file.write_text(render_error(ticker, today, exc))
        print(f"Run failed for {ticker}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
