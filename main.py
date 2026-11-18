"""cbBTC 30-minute breakout trend bot for agent-fun/bars-replay/v1.

Strategy (one asset, CBBTC, long only, full size, at most one position):
  * Entry: a 30-minute return breakout. Buy with all cash when, on the latest
    1-minute bar close, the 30-bar return is >= +50 bps, the 60-bar return is
    >= 0, the close sits above its 60-bar EMA and the 20-bar EMA sits above
    the 60-bar EMA (trend confirmation). The entry rides multi-hour trends
    and ignores chop: a 50 bps / 30 min move is far above the ~6.7 bps
    1-minute noise, so the signal fires only a few times per day.
  * Exit: sell the whole position when any of these hits, measured from the
    filled entry price against the latest close:
      - target  +200 bps,
      - stop    -60 bps,
      - trailing stop: once the peak gain reaches +30 bps, sell if the gain
        falls 25 bps below that peak,
      - time stop: 120 bars held.
  * Guards: no trading during warm-up batches, no new buy in the last 40
    bars of the (published 1,440-bar) window, max_slippage_bps 100 on every
    order, at most one order per reply.

Only the standard library is used. No network, no wall clock, no randomness:
the same bars always produce the same orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
MAX_SLIPPAGE_BPS = 100

# Entry thresholds (basis points).
BREAKOUT_BPS = 50        # 30-bar return must reach this
TREND_60_BPS = 0         # 60-bar return must be at least this
# Exit thresholds (basis points, vs filled entry price).
TARGET_BPS = 200
STOP_BPS = 60
TRAIL_ARM_BPS = 30
TRAIL_GIVEBACK_BPS = 25
MAX_HOLD_BARS = 120
# History / window guards.
MIN_BARS = 60            # bars needed before the EMAs are trusted
NO_BUY_LAST_BARS = 40    # do not open a position this close to the window end
WINDOW_BARS = 1440       # published window length of every phase

EMA_FAST_LEN = 20
EMA_SLOW_LEN = 60


class Bot:
    def __init__(self):
        self.closes = []          # closes as ints, oldest first
        self.ema_fast = None      # float EMA(20) of closes
        self.ema_slow = None      # float EMA(60) of closes
        self.entry_price = None   # filled buy price (raw units), None when flat
        self.entry_qty = 0
        self.peak_gain_bps = 0.0  # best gain since entry, bps
        self.hold_bars = 0
        self.pending_buy_id = None

    def _update_indicators(self, close):
        self.closes.append(close)
        if self.ema_fast is None:
            self.ema_fast = float(close)
            self.ema_slow = float(close)
        else:
            a_fast = 2.0 / (EMA_FAST_LEN + 1)
            a_slow = 2.0 / (EMA_SLOW_LEN + 1)
            self.ema_fast = a_fast * close + (1.0 - a_fast) * self.ema_fast
            self.ema_slow = a_slow * close + (1.0 - a_slow) * self.ema_slow

    def _ret_bps(self, bars_back):
        if len(self.closes) <= bars_back:
            return None
        now = self.closes[-1]
        then = self.closes[-1 - bars_back]
        return (now - then) * 10000.0 / then

    def on_batch(self, state, batch):
        # Learn the outcome of the order decided on the previous batch.
        for fill in batch.get("fills", []):
            if fill.get("client_id") == self.pending_buy_id and fill.get("status") == "filled":
                self.entry_price = int(fill["price"])
                self.entry_qty = int(fill["qty"])
                self.peak_gain_bps = 0.0
                self.hold_bars = 0
        self.pending_buy_id = None

        if state.warming_up:
            return []

        bar = None
        for b in batch.get("bars", []):
            if b.get("symbol") == SYMBOL:
                bar = b
                break
        if bar is None:
            return []  # gap minute: no new information, no decision
        close = int(bar["c"])
        self._update_indicators(close)

        holding = state.positions.get(SYMBOL)
        is_holding = holding is not None and holding.qty > 0

        if is_holding:
            if self.entry_price is None:
                # Position held but entry price unknown (should not happen):
                # derive a cost basis from the position instead of trading blind.
                cost = holding.cost
                qty = holding.qty
                # cost is quote units; price = cost * 10^(qty+price scale) / (qty * 10^quote scale)
                self.entry_price = cost * 10 ** 13 // (qty * 10 ** 6) if qty else close
                self.entry_qty = qty
            gain_bps = (close - self.entry_price) * 10000.0 / self.entry_price
            if gain_bps > self.peak_gain_bps:
                self.peak_gain_bps = gain_bps
            self.hold_bars += 1
            sell = (
                gain_bps >= TARGET_BPS
                or gain_bps <= -STOP_BPS
                or (self.peak_gain_bps >= TRAIL_ARM_BPS
                    and gain_bps <= self.peak_gain_bps - TRAIL_GIVEBACK_BPS)
                or self.hold_bars >= MAX_HOLD_BARS
            )
            if sell:
                qty = holding.qty
                self.entry_price = None
                self.entry_qty = 0
                return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            return []

        # Flat: look for the breakout entry.
        if len(self.closes) < MIN_BARS:
            return []
        last_bar = state.warmup_bars + WINDOW_BARS - NO_BUY_LAST_BARS
        if state.seq >= last_bar:
            return []
        ret30 = self._ret_bps(30)
        ret60 = self._ret_bps(60)
        if ret30 is None or ret60 is None:
            return []
        if (ret30 >= BREAKOUT_BPS
                and ret60 >= TREND_60_BPS
                and close > self.ema_slow
                and self.ema_fast >= self.ema_slow):
            notional = state.cash
            if notional < 1_000_000:
                return []
            cid = state.client_id()
            self.pending_buy_id = cid
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": notional,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS,
                     "client_id": cid}]
        return []


_BOT = Bot()


def on_batch(state, batch):
    return _BOT.on_batch(state, batch)


makefun_bars.run(on_batch)
