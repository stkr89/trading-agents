# trading-agents

A daily-scheduled GitHub Actions pipeline that runs the [TradingAgents](https://github.com/TauricResearch/TradingAgents) multi-agent LLM framework against the Mag 7 stocks, posts each decision as a GitHub issue, and submits the corresponding paper trade to Alpaca.

This is a **research and learning project**. TradingAgents is research software, decisions are non-deterministic, and trades are paper-only. Not financial advice.

## What it does

Every weekday at 9:00 AM New York time:

1. A `schedule-guard` job checks NY local time and the NYSE calendar (skips weekends, DST shifts, and market holidays)
2. If the gate passes, 7 parallel jobs run — one per Mag 7 ticker (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA)
3. Each job runs the TradingAgents pipeline (4 analysts → bull/bear debate → trader → risk team → portfolio manager)
4. The portfolio manager outputs a 5-tier rating: Buy, Overweight, Hold, Underweight, or Sell
5. A second LLM call generates a plain-English summary of the decision
6. The rating is mapped to an Alpaca paper trade per the strategy rule (below)
7. A GitHub issue is created with the trade summary, the rating, the plain-English explanation, and collapsible sections for the full analyst reports / debate / risk discussion

## Strategy rule (paper trading)

| Rating | Action |
|---|---|
| Buy | Add ~$2,000 worth |
| Overweight | Add ~$1,000 worth |
| Hold | No change |
| Underweight | Sell ~$1,000 worth (capped at current position; no shorting) |
| Sell | Sell ~$2,000 worth (capped at current position; closes out fully if smaller) |

Long-only by design. Selling is always clamped at zero — the bot never goes short.

### Risk caps (applied to BUYS only)

| Cap | Default | Purpose |
|---|---|---|
| `MAX_POSITION_PCT` | 20% | Max % of portfolio that any single ticker can occupy. Prevents one stock from dominating. |
| `MAX_TOTAL_EXPOSURE_PCT` | 80% | Max % of portfolio that can be long at once. Forces a cash buffer; prevents margin usage. |

Both caps are percentages of the live `portfolio_value`, so they scale with the account — a 20% cap means $20K when you have $100K and grows to $24K if your portfolio grows to $120K. Buy orders are scaled down to fit inside both caps. If a buy would be capped to $0 (already at limit), it is skipped entirely and the trade summary explains why. Both constants live at the top of [scripts/execute_trade.py](scripts/execute_trade.py) and are easy to tune.

## File layout

```
.github/workflows/
  daily-analysis.yml          Cron + matrix + DST/holiday guard + Alpaca trade step

scripts/
  check_should_run.py         DST + NYSE calendar gate (decides whether the matrix runs)
  run_analysis.py             Calls TradingAgents.propagate(), generates plain-English summary,
                              renders the issue body markdown
  execute_trade.py            Reads the rating, submits the Alpaca paper trade per the strategy rule

requirements.txt              Pulls TradingAgents from the upstream repo + alpaca-py
```

## Required GitHub repo secrets

Set these under Settings → Secrets and variables → Actions:

| Secret | Purpose |
|---|---|
| `OPENAI_API_KEY` | Powers the TradingAgents LLM calls (deep + quick models) and the plain-English summarizer |
| `ALPACA_API_KEY` | Alpaca paper trading API key ID |
| `ALPACA_SECRET_KEY` | Alpaca paper trading API secret |

Sign up for Alpaca paper at [alpaca.markets](https://alpaca.markets) — paper accounts come with $100K virtual balance and no credit card requirement.

## Models in use

| Role | Model |
|---|---|
| Deep-thinking (PM, debate judges) | `gpt-5.4` |
| Quick-thinking (analysts, summary) | `gpt-5.4-mini` |

Configured in [scripts/run_analysis.py](scripts/run_analysis.py). Swap providers/models by editing the config block.

Approximate cost: ~$0.05-$0.15 per ticker per run, roughly $40-150/year for the full Mag 7 daily schedule.

## Triggering

**Automatic:** weekday cron at 9:00 AM NY (handled by the workflow).

**Manual:** Actions tab → "Daily Trading Analysis" → Run workflow. Optionally provide a single ticker name (AAPL, NVDA, etc.) to run just that one. Manual triggers bypass the DST and NYSE-holiday guards.

## Inspecting output

| What | Where |
|---|---|
| Today's decision per ticker | Repo Issues tab (filter by label `daily-analysis`) |
| Full reasoning chain (analyst reports, debate, risk discussion) | Inside each issue, in the collapsible sections |
| Current paper portfolio | [Alpaca paper dashboard](https://app.alpaca.markets/paper) |
| TradingAgents memory log + per-run state JSONs | Actions tab → workflow run → Artifacts → `tradingagents-state-<TICKER>-<DATE>.zip` |
| Workflow run history / failures | Actions tab |

## Persistence

The TradingAgents memory log (`~/.tradingagents/memory/trading_memory.md`) is cached per-ticker between runs using `actions/cache`. This is what enables the framework's reflection feature — yesterday's decision gets scored against forward returns and a one-paragraph reflection is fed back into tomorrow's PM prompt for the same ticker.

GitHub Actions evicts caches after 7 days of inactivity. The memory log is also uploaded as an artifact for 30 days, but artifacts are read-only snapshots — only the cache feeds back into runs.

## Disclaimers

- TradingAgents is explicitly designed for research, not real-money trading
- Multi-agent LLM trading frameworks have no peer-reviewed evidence of consistent live outperformance
- All trading in this project is paper money via Alpaca's simulator
- Decisions are non-deterministic — running the same ticker twice in one day can produce different ratings
- Nothing in this repo is investment advice
