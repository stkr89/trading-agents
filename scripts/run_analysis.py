"""Run TradingAgents for one ticker and write the decision to a markdown file.

Reads:
  TICKER          - ticker symbol (e.g. NVDA)
  GOOGLE_API_KEY  - Gemini API key
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


def render_decision(ticker: str, date: str, decision) -> str:
    """Format the decision as markdown. Decision shape varies by version, so be defensive."""
    if isinstance(decision, dict):
        body = "\n".join(f"**{k}**: {v}" for k, v in decision.items())
    else:
        body = f"```\n{decision}\n```"
    return (
        f"# {ticker} — {date}\n\n"
        f"_Generated {datetime.now(ZoneInfo('America/New_York')).isoformat(timespec='seconds')} (NY)_\n\n"
        "## Decision\n\n"
        f"{body}\n"
    )


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
        config["llm_provider"] = "google"
        config["deep_think_llm"] = "gemini-2.5-flash-lite"
        config["quick_think_llm"] = "gemini-2.5-flash-lite"
        config["max_debate_rounds"] = 1
        config["online_tools"] = True

        ta = TradingAgentsGraph(debug=False, config=config)
        _, decision = ta.propagate(ticker, today)
        output_file.write_text(render_decision(ticker, today, decision))
        print(f"Wrote decision for {ticker} to {output_file}")
        return 0
    except Exception as exc:
        output_file.write_text(render_error(ticker, today, exc))
        print(f"Run failed for {ticker}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
