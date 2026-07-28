# Project Aegis AI Studio

## SMC + Astronacci Pro Scalper (TradingView Indicator)

`indicators/SMC_Astronacci_Scalping_Reversal.pine` is a Pine Script v5 indicator that
flags reversal-scalping setups using a top-down, multi-timeframe workflow:

1. **Bias comes from the higher timeframe (HTF).** Market structure (BOS/CHoCH) is
   computed on a configurable HTF and read back with `request.security` using the
   last *closed* HTF bar, so the bias does not repaint.
2. **Entries are found on the chart timeframe (LTF).** A signal only fires when the
   LTF structure shift agrees with the HTF bias — counter-trend entries (e.g. a BUY
   while the HTF is bearish) are suppressed.
3. **The trigger is the Fibonacci OTE zone.** Price tapping the 0.618–0.786
   retracement of the active structure leg is what fires the arrow.

### What it draws

| Component | Behaviour |
|---|---|
| Swing structure line | Alternating zigzag between confirmed pivots, capped at 50 segments |
| BOS / CHoCH | Dashed level + label at the broken swing; only the last N events are kept |
| Order Blocks | Last opposing candle before a break; box extends live and is deleted once mitigated |
| Fair Value Gaps | 3-bar imbalance; box extends live and is deleted once filled |
| Liquidity sweeps | Small triangle where a wick takes a swing point and the body closes back inside |
| Fibonacci OTE zone | "Golden Zone" box on the active leg, following the live structure |
| Fibonacci time marks | Fibonacci bar counts projected from each CHoCH, tagged with moon-phase glyphs |
| Dashboard | HTF bias, LTF bias, alignment, last event, zone status, sweep status |

### How to use it

1. TradingView → **Pine Editor** → paste the file contents → **Save** → **Add to Chart**.
2. Set the HTF to roughly 4–12× your chart timeframe:

   | Chart TF | HTF Timeframe | Swing Pivot Length |
   |---|---|---|
   | M1 | 15 | 8 |
   | M5 | 60 | 8 |
   | M15 | 240 | 8–13 |

3. Trade only when the dashboard shows **Aligned ✔**. The background tint reflects the
   HTF bias — green means look for longs only, red means look for shorts only.
4. Use the built-in `alertcondition`s (**Add Alert** → condition = this indicator) instead
   of watching the chart.
5. Tuning: raise *LTF Swing Pivot Length* if signals are too frequent; enable
   *Require recent liquidity sweep* for stricter, higher-conviction entries only.

This is a technical-analysis tool, not financial advice. Validate it on historical data
and demo/paper trade before risking real capital.
