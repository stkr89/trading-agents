"""Submit a paper trade to Alpaca based on the day's rating.

Strategy rule (long-only, clamp at zero):
  Buy         -> add $2,000 worth
  Overweight  -> add $1,000 worth
  Hold        -> no change
  Underweight -> sell $1,000 worth (capped at current position value)
  Sell        -> sell $2,000 worth (capped at current position value)

Reads:
  TICKER             - ticker symbol
  ALPACA_API_KEY     - Alpaca paper API key
  ALPACA_SECRET_KEY  - Alpaca paper API secret
  RATING_FILE        - file containing just the rating word (default: rating.txt)
  TRADE_OUTPUT_FILE  - markdown summary path (default: trade.md)

Always writes a markdown summary so the issue can include the trade outcome.
Returns 0 on success, 1 on any failure.
"""

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RATING_TO_DELTA = {
    "Buy": 2000.0,
    "Overweight": 1000.0,
    "Hold": 0.0,
    "Underweight": -1000.0,
    "Sell": -2000.0,
}


def write_summary(
    file: Path,
    ticker: str,
    rating: str,
    *,
    action: str | None = None,
    error: str | None = None,
    details: dict | None = None,
) -> None:
    now = datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    lines = [
        f"## 💼 Paper Trade — {ticker}",
        "",
        f"_Submitted {now} (NY)_",
        "",
        f"**Rating:** {rating}",
    ]
    if error:
        lines += ["**Status:** ❌ Error", "", f"```\n{error}\n```"]
    else:
        lines.append(f"**Status:** ✅ {action}")
        if details:
            lines += ["", "**Account snapshot:**"]
            for label, value in details.items():
                if isinstance(value, (int, float)):
                    lines.append(f"- {label}: ${value:,.2f}")
                else:
                    lines.append(f"- {label}: {value}")
    lines.append("")
    file.write_text("\n".join(lines))


def main() -> int:
    ticker = os.environ["TICKER"].strip().upper()
    rating_file = Path(os.environ.get("RATING_FILE", "rating.txt"))
    output_file = Path(os.environ.get("TRADE_OUTPUT_FILE", "trade.md"))

    if not rating_file.exists():
        write_summary(output_file, ticker, "(missing)", error=f"Rating file {rating_file} not found.")
        return 1

    rating = rating_file.read_text().strip()
    if rating not in RATING_TO_DELTA:
        write_summary(output_file, ticker, rating, error=f"Unrecognised rating '{rating}'. No trade submitted.")
        return 1

    delta = RATING_TO_DELTA[rating]

    if delta == 0:
        write_summary(output_file, ticker, rating, action="No action — Hold rating.", details={})
        return 0

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        write_summary(output_file, ticker, rating, error="ALPACA_API_KEY or ALPACA_SECRET_KEY not set.")
        return 1

    try:
        from alpaca.common.exceptions import APIError
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestTradeRequest
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        trading = TradingClient(api_key, secret_key, paper=True)
        data = StockHistoricalDataClient(api_key, secret_key)

        try:
            position = trading.get_open_position(ticker)
            current_qty = float(position.qty)
            current_value = float(position.market_value)
        except APIError:
            current_qty = 0.0
            current_value = 0.0

        latest = data.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=ticker))
        last_price = float(latest[ticker].price)

        if delta > 0:
            qty = round(delta / last_price, 6)
            trading.submit_order(
                MarketOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                )
            )
            action = f"Submitted **BUY** {qty} shares (~${delta:,.2f} at ~${last_price:,.2f})"
        else:
            sell_dollars = abs(delta)
            if current_value <= 0:
                action = f"Skipped SELL — no current position to sell (rule wanted -${sell_dollars:,.2f})"
            elif sell_dollars >= current_value:
                trading.close_position(ticker)
                action = (
                    f"Submitted **CLOSE** entire position: {current_qty} shares "
                    f"(~${current_value:,.2f}; rule wanted -${sell_dollars:,.2f}, capped at current position)"
                )
            else:
                qty = min(round(sell_dollars / last_price, 6), current_qty)
                trading.submit_order(
                    MarketOrderRequest(
                        symbol=ticker,
                        qty=qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.DAY,
                    )
                )
                action = f"Submitted **SELL** {qty} shares (~${qty * last_price:,.2f} at ~${last_price:,.2f})"

        account = trading.get_account()
        details = {
            "Position before this trade": current_value,
            "Buying power": float(account.buying_power),
            "Portfolio value": float(account.portfolio_value),
            "Cash": float(account.cash),
        }
        write_summary(output_file, ticker, rating, action=action, details=details)
        return 0
    except Exception as exc:
        write_summary(
            output_file,
            ticker,
            rating,
            error=f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}",
        )
        print(f"Trade execution failed for {ticker}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
