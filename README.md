# TiresIAs

**Can you copy what makes the best investors win — and still win once you know it?**

TiresIAs tests that question without shortcuts. Every hypothesis and threshold is committed to git before the data
that decides it is downloaded, every published result is reproduced before it is extended, and negative results are
reported as prominently as positive ones.

## Where it stands

| Phase | Question | Verdict |
|---|---|---|
| 1 | Does a foundation model for candlesticks (Kronos) forecast anything tradable? | **No** · 0 of 5 tests |
| 2A | Can *Buffett's Alpha* be reproduced from public data? | **Yes** · 3 of 3 |
| 2A′ | Does Buffett's factor recipe still work after it was published? | **Partly** · ahead of the market in 2012–19, not in 2019–26 |
| 2B | Does the recipe of the best 13F managers, picked without hindsight, beat the S&P 500? | **No** · 1 of 4 |
| 3A | Do the Hyperliquid traders winning *now* keep winning? | **No** · 1 of 2 |
| 3C | Does copying the right members of Congress beat the S&P 500? | Running |

Results: [phase 1](docs/RESULTADOS_RONDA2.md) · [2A and 2A′](docs/RESULTADOS_FASE2A.md) · [2B](docs/RESULTADOS_FASE2B.md) · [3](docs/RESULTADOS_FASE3.md).
Plans: [phase 2](docs/PLAN_FASE2.md) · [phase 3](docs/PLAN_FASE3.md). Documents are in Spanish.

## What we have learned

- **Buffett is mostly factors.** Adding low beta (BAB) and quality (QMJ) to the usual four factors cuts Berkshire's
  alpha from 10.0 % to 4.0 % a year, and it stops being significant, as the paper found.
- **Picking the best managers doesn't beat the index.** The factor recipe of the top-decile 13F managers, chosen
  without hindsight from 12,473 filers, returned a Sharpe ratio of 0.79 in 2019–2026 against 0.83 for the S&P 500
  with dividends; an oracle that knew next quarter's winners reached 2.28, so the machinery can see skill when it
  exists.
- **Yesterday's leaders are tomorrow's laggards.** On Hyperliquid, the top 10 % of traders over six months earned half
  as much as randomly chosen traders over the next six; the extremes, winners and losers, did worst.
- **Copying holdings has not paid.** The Global X Guru ETF, which copies hedge funds' 13F positions, returned 5.9 % a
  year against 10.8 % for the S&P 500 over ten years ([PortfoliosLab](https://portfolioslab.com/tools/stock-comparison/GURU/SPY)).
  NANC, the ETF that copies Democratic members of Congress, beat the S&P 500 from 2023 to 2026 only through extra
  market exposure: beta 1.08, alpha 0.0 %.
- **Free market data fails silently.** Alpaca's history API can return another company's prices for a reused ticker,
  splice two companies into one series, pad gaps with zero-volume bars and drop symbols from batch requests; the SEC
  regenerated its 13F datasets in 2024. Each trap, and the check that catches it, is in
  [`tiresias/precios.py`](tiresias/precios.py).

## How the work is done

- **Pre-registered.** Criteria are fixed in git before the deciding data exists.
- **Replicate first.** A published result is reproduced as its authors computed it before it is extended.
- **Against chance.** Every effect is compared with a placebo: the same procedure where it cannot work.
- **No hindsight.** Portfolios are formed on the date the information became public.

## Run it

```bash
python3.12 -m venv ~/.venvs/tiresias && source ~/.venvs/tiresias/bin/activate
pip install -r requirements.txt
python -m pytest tests        # 197 tests
python -m tiresias.buffett     # phases 2A and 2A′
```

Phase 2A reads, from `~/tiresias_datos/fase2/crudo`, the Fama-French factors and momentum (Kenneth R. French Data
Library), BAB and QMJ (AQR Data Sets) and BRK-A daily prices. No data is stored in the repository.

---

TiresIAs began in October 2026 as a fork of [Kronos](https://github.com/shiyu-coder/Kronos) to evaluate it, and is now
an independent project; the Kronos code is kept under its MIT licence so that phase 1 stays reproducible
([origin](docs/ORIGEN_KRONOS.md)). MIT licence. Research only, not investment advice.
