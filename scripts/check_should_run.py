"""Decide whether today's daily-analysis run should proceed.

Run by the workflow's guard job. Writes proceed=true|false to $GITHUB_OUTPUT
and prints a one-line reason to stdout for the run logs.

Skips when:
- Cron fires at the wrong UTC hour (DST safety net — only proceed if NY hour == 09)
- Today is not a NYSE trading day (weekends already filtered by cron, but holidays still fire)

Always proceeds for manual workflow_dispatch — useful for testing on weekends/holidays.

Fails closed: if the NYSE calendar lookup throws, we skip rather than risk
running on a holiday with stale market data.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo


def write_output(value: str, message: str) -> None:
    print(message)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"proceed={value}\n")


def main() -> int:
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        write_output("true", "Manual trigger — proceeding regardless of hour or holiday.")
        return 0

    ny_now = datetime.now(ZoneInfo("America/New_York"))
    ny_today = ny_now.date()

    if ny_now.hour != 9:
        write_output(
            "false",
            f"NY local hour is {ny_now.hour:02d}:00 (not 09:00) — DST guard skipping.",
        )
        return 0

    try:
        import pandas_market_calendars as mcal

        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(start_date=ny_today, end_date=ny_today)
    except Exception as exc:
        write_output(
            "false",
            f"NYSE calendar lookup failed ({type(exc).__name__}: {exc}) — skipping out of caution.",
        )
        return 0

    if schedule.empty:
        write_output("false", f"{ny_today} is not a NYSE trading day (holiday/weekend) — skipping.")
        return 0

    write_output("true", f"{ny_today} is a NYSE trading day at 09:00 NY — proceeding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
