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


def render_decision(ticker: str, date: str, rating, final_state: dict) -> str:
    """Format the decision as markdown: rating + the PM's full narrative."""
    narrative = (final_state or {}).get("final_trade_decision") or "_(no narrative returned)_"
    rating_str = rating if isinstance(rating, str) else str(rating)
    return (
        f"# {ticker} — {date}\n\n"
        f"_Generated {datetime.now(ZoneInfo('America/New_York')).isoformat(timespec='seconds')} (NY)_\n\n"
        f"**Rating:** {rating_str}\n\n"
        "## Portfolio Manager Decision\n\n"
        f"{narrative}\n"
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
        config["llm_provider"] = "openai"
        config["deep_think_llm"] = "gpt-5.4"
        config["quick_think_llm"] = "gpt-5.4-mini"
        config["max_debate_rounds"] = 1
        config["online_tools"] = True

        ta = TradingAgentsGraph(debug=False, config=config)
        final_state, decision = ta.propagate(ticker, today)
        output_file.write_text(render_decision(ticker, today, decision, final_state))
        print(f"Wrote decision for {ticker} to {output_file}")
        return 0
    except Exception as exc:
        output_file.write_text(render_error(ticker, today, exc))
        print(f"Run failed for {ticker}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
