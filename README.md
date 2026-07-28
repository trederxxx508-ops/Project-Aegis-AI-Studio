# Project Aegis AI Studio

## SMC + Astronacci Reversal Scalper (TradingView Indicator)

`indicators/SMC_Astronacci_Scalping_Reversal.pine` is a Pine Script v5 indicator for TradingView that flags potential trend reversals for scalping by combining:

- **Smart Money Concepts (SMC)**: swing-based market structure with BOS (Break of Structure) / CHoCH (Change of Character) detection, Order Blocks, Fair Value Gaps, and liquidity sweep (stop-hunt) marking.
- **Astronacci-style Fibonacci analysis**: a dynamic Fibonacci "Optimal Trade Entry" (OTE) retracement zone (default 0.618–0.786) drawn on the current structure leg, plus Fibonacci-sequence time-cycle lines projected from each confirmed CHoCH to flag likely reversal timing windows. (Independent implementation of the public Fibonacci concepts this style is based on — not affiliated with or endorsed by Astronacci Int'l.)

### How to use it

1. Open TradingView → Pine Editor → paste the contents of the `.pine` file → **Add to Chart**.
2. Use it on a low timeframe (1m–15m) for scalping; the swing pivot length input controls how reactive the structure detection is (lower = faster/noisier).
3. A bullish/bearish triangle signal fires when price first taps into the Fibonacci OTE zone after a confirmed CHoCH/BOS in that direction (optionally require a recent liquidity sweep too, via the input toggle).
4. Right-click the signal → **Add Alert** (or use the built-in `alertcondition`s) to get notified in real time instead of watching the chart.
5. Order Blocks, Fair Value Gaps, and sweep labels are shown for visual confluence/context and are not required for the signal unless you enable the corresponding confluence toggles.

This is a technical-analysis tool, not financial advice — validate on historical data and demo/paper trade before using it with real capital.
