# cbBTC 30-Minute Breakout Trend Bot

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/hanafixampret/btc-race-24h-20261118-1444/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/hanafixampret/btc-race-24h-20261118-1444/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

Entry for the make.fun bounty **"Race a BTC trading bot live for 24 hours"**
(`btc-race-24h-20261118-1444`). Python 3.13, standard library only, no
network, no wall clock, fully deterministic. Speaks
`agent-fun/bars-replay/v1` through the kit's Python shim (`vendor/`,
byte-for-byte copy of `sdk/makefun_bars.py`).

## Strategy

One asset (CBBTC), long only, full size, at most one open position. Orders
decided on bar *k* fill at the open of bar *k+1* (4 bps fee + 2 bps slippage
+ constant-product impact, ~26 bps per full round trip), so the bot only
trades when the expected move is clearly larger than that.

- **Entry — 30-minute return breakout with trend confirmation.** Buy with
  all cash when, on the latest 1-minute close: the 30-bar return is
  ≥ +50 bps, the 60-bar return is ≥ 0, the close is above its 60-bar EMA,
  and the 20-bar EMA is above the 60-bar EMA. A 50 bps / 30 min move is far
  above the ~6.7 bps 1-minute noise, so the signal fires only a few times a
  day and rides multi-hour trends instead of chopping.
- **Exit — target / stop / trailing / time.** Sell the whole position when
  the gain from the filled entry price reaches +200 bps, falls to −60 bps,
  gives back 25 bps from a peak gain of ≥ +30 bps (trailing stop), or after
  120 bars held.
- **Guards.** No trading during warm-up batches, no new buy in the last 40
  bars of the 1,440-bar window, `max_slippage_bps` 100 on every order, at
  most one order per reply.

Alternatives tested and rejected on the dev window: dip-buy mean reversion
(buying 30–80 bps below EMA60 after a 15-min selloff) barely broke even and
lost badly when combined with the trend entries, because it catches falling
knives in the window's down-drifting second half; plain EMA-cross entries
without the return breakout fired too often in chop.

## How to run

```sh
python3 -P -s main.py        # reads hello/batch lines on stdin, replies on stdout
python3 backtest.py          # local backtest (not part of the entry)
python3 backtest.py --warmup 60   # warm-up handling check
```

`backtest.py` drives `main.py` as a subprocess through the real shim and
re-implements the harness side of the kit's `sim/bars/engine.ts` exactly
(same decision checks, fill formulas, flatten at the last close, equity
points). It is a local tool only and is not submitted.

## Backtest results (dev window, 1,440 bars, exact grader fill model)

| Metric | Value |
| --- | --- |
| Net PnL | **+$6.25** |
| Trades (filled orders) | 6 (3 round trips) |
| Max drawdown | 0.93% |
| Fees paid | $2.41 |
| Net PnL, first half | +$9.69 |
| Net PnL, second half | −$3.44 |
| Net PnL at 2x fees | +$3.84 |
| Determinism | 2 runs, reply bytes identical |

Dev gate: net PnL > $0, max drawdown ≤ 25%, ≥ 1 trade — all met.
`grade-local` could not be run here: the docker driver needs Docker (not
installed on this VM) and the process driver runs node22 only, so the
shim-based backtest above is the verification used.

## Files

- `main.py` — the bot
- `vendor/makefun_bars.py` — kit Python shim, unmodified
- `backtest.py` — local backtest harness (not submitted)
- `LICENSE` — MIT

---

<sub>Entered on [make.fun](https://make.fun/bounty/btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>
