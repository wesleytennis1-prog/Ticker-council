---
name: stock-deep-dive
description: Full equity valuation and Buy/Sell/Hold call for a single ticker. Trigger whenever the user's message is just a ticker symbol (e.g. "NVDA", "D05.SI", "ES3") or asks for a deep dive / valuation of one stock.
---

# Stock deep-dive playbook

One stock per run. User is SG-based (SGD, UK English), invests via IBKR, visual learner.
Tone: sell-side initiation note written by an experienced PM. No filler, no em dashes.

## 1. Data collection (do steps in parallel where possible)

**IBKR (primary for market data and the user's book)**
- `search_contracts` → pick exact symbol, primary listing (US unless user's ticker implies SGX/LSE/HK).
- `get_price_snapshot` fields: last, bid_ask, change, prior_close, volume, misc_statistics,
  dividend_yield, historical_vol, implied_vol_underlying, implied_volatility_percentile,
  year_to_date_change, cumulative_perf_1m, cumulative_perf_1y, cumulative_perf_3y, cumulative_perf_5y, top_status.
- `get_price_history` ONE_YEAR / ONE_DAY bars (and FIVE_YEARS / ONE_WEEK) → compute 50/200dma, drawdown, beta proxy vs SPY.
- `get_company_themes`, `get_company_connections` for competitors/suppliers/customers.
- `get_account_positions` → if the user holds the stock or options on it, state position, cost basis, P&L, and tailor the call (add / trim / hold / roll covered calls).
- Note whether quotes are REALTIME or DELAYED.

**Web (fundamentals, filings, consensus)** via WebSearch/WebFetch:
- Latest 10-K/10-Q (or annual report / SGX filings), latest earnings release + call highlights, guidance.
- Sources to try: SEC EDGAR, company IR, stockanalysis.com (financials, ratios, statistics), macrotrends,
  finviz, Yahoo Finance, marketscreener (consensus), SGX/SGinvestors for Singapore names.
- 5y history of: revenue, gross/op/net margin, EPS, CFO, capex, FCF, SBC, shares outstanding,
  cash, debt, leases, dividends, buybacks.
- Consensus: next 2 FY revenue/EPS/EBITDA, analyst target range, rating distribution.
- Recent news (last 90 days), insider transactions, short interest, upcoming catalysts and earnings date.
- Peer set: 4-7 true comps. Pull fwd P/E, EV/EBITDA, EV/Sales, P/FCF, growth, margins, ROIC for each.
- Current 10y UST yield (rf) and use ERP 4.5-5.5%.

Cross-check every key number against a second source when they disagree; state the one used.
Never invent numbers. If something cannot be found, say so in the report.

## 2. Analysis ("leave no stone unturned")

1. **Business**: what it sells, segments and mix, geography, moat (rate it: none/narrow/wide, with why), management and capital allocation record.
2. **Income statement**: growth trajectory, margin structure and operating leverage, quality of earnings (SBC, one-offs, non-GAAP gap).
3. **Balance sheet**: net debt/EBITDA, interest cover, liquidity, maturities, goodwill share of assets, working capital trend (DSO/DIO/DPO).
4. **Cash flow**: CFO vs net income (accrual ratio), capex intensity, FCF conversion, SBC-adjusted FCF, buyback vs dilution.
5. **Returns**: ROE, ROIC vs WACC, DuPont.
6. **Health scores**: Piotroski F-score, Altman Z (non-financials), Beneish M if warranted.
7. **Valuation**:
   - Build `inputs.json` in the scratchpad and run `python3 -I equity/valuation.py <inputs.json>`.
   - Bear/base/bull 5y DCF with explicit growth + FCF margin paths tied to consensus and history; probabilities must sum to 1.
   - Reverse DCF: what growth the price implies; is it achievable?
   - WACC x terminal growth sensitivity grid.
   - Relative valuation: peer median multiples, subject's premium/discount vs peers and vs own 5y average, and whether the premium is earned (growth, margins, ROIC).
   - Banks/insurers/REITs: swap DCF for P/B vs ROE (Gordon), DDM, P/NAV, dividend yield and DPU. Adjust the engine inputs or do it by hand.
8. **Technicals and positioning**: trend vs 50/200dma, 52w range position, RSI-style momentum, IV vs HV, short interest.
9. **Risks and catalysts**: top 5 risks with probability/impact, upcoming catalysts with dates. What would change the call.

## 2b. The Council (Ticker Council-style layer)

Twelve seats, each reading one data feed, each voting on three horizons (week, 3 months, year)
with a score in [-1, 1] (|score| ≥ 0.15 = up/down, else even; magnitude = conviction).
Score each seat from evidence, not vibes, and give 2-4 numeric reasons per seat.

| Seat | Reads |
|---|---|
| Price Chart | IBKR history: 20/50/200dma, RSI, volume on up vs down days |
| Financials | growth, margins, debt, ROIC |
| Analyst Targets | rating mix, mean/range of targets, recent changes |
| Earnings Estimates | 30/90-day EPS revisions, beat record |
| Insider Trades | Form 4 (openinsider / secform4): buys vs sells, 10b5-1 or discretionary |
| Congress Trades | capitoltrades / quiverquant disclosures (note ~30-45 day lag) |
| News | last 14 days of headlines and dated upcoming events |
| SEC Filings | buybacks, dilution, new debt, litigation, concentration (10-Q/8-K) |
| Institutional Holdings | 13F changes, short interest, days to cover |
| Options Market | IBKR: IV vs HV, IV percentile, put/call; skew if available |
| Economy | rates path, inflation, ISM/PMI, sector sensitivity |
| Related Markets | sector ETF, peer basket, index, overseas session (5d and 1m) |

Non-US names: Congress seat votes even with "not applicable"; swap Form 4 for local director-dealing filings (SGX/HKEX/RNS).

Then the debate: bull case (3 points, price = bull DCF), bear case (3 points, price = bear DCF),
challenger (holes in both), verdict (judge, 2-3 sentences consistent with the rating).

Business check inputs: revenue growth bars (last 2 FY + latest quarter YoY), operating margin
from→to, FCF YoY and SBC-adjusted FCF margin, PEG, consensus 5y growth, 3m price change, 3m EPS revision,
room to analyst mean target.

Price fan: `price.sigma` = annualised vol (use IBKR implied_vol_underlying, else historical_vol);
`price.history` = IBKR 1y daily closes as [date, close]. The year fan centres on the 12m target.

**Build:** copy `equity/sample_council_inputs.json` as the schema, fill it with real data
(set `meta.sample` false, `meta.quote_status` REALTIME/DELAYED, `call.target`, `scenarios`, `football`, `comps`,
`financials`, `ratios`, `health`, `risks`, `catalysts`, `change_my_mind`, `sources`), then run:
```
python3 -I equity/valuation.py <TICKER>-<date>-inputs.json > <TICKER>-<date>-valuation.json
python3 -I equity/council.py <TICKER>-<date>-council.json <TICKER>-<date>-valuation.json equity/reports/<TICKER>-<date>.html
python3 -I equity/ledger.py add equity/reports/<TICKER>-<date>.data.json
```
Publish the HTML as an Artifact (icon "chart"). The template already covers council, fan, seats, debate,
business check, valuation, books, risks, sources: do not hand-write a separate report page.

**Accuracy tracking:** at the start of every run, `ledger.py due` lists matured calls; fetch the closing
price on each due date from IBKR, `ledger.py score <id> <horizon> <price>`, then `ledger.py stats`
(writes calibration.json, which reweights seats automatically). Report the running hit rate in one line.

## 3. Rating rule

Blended fair value = DCF (prob-weighted) and multiples, default 50/50 (state any change and why).
- BUY: upside ≥ 15%
- HOLD: -10% < upside < 15%
- SELL: upside ≤ -10%
Override only with a stated reason (e.g. balance-sheet risk, broken thesis, momentum regime). Give a 12-month price target and a "good entry" price (fair value with 20% margin of safety).

## 4. Output

**Chat (keep tight):**
1. Headline box: ticker, name, price (time, realtime/delayed, + SGD equivalent), rating, 12m target, upside %, conviction (low/med/high), one-line thesis.
2. Scorecard table: valuation, growth, profitability, balance sheet, momentum, each scored 1-5.
3. Valuation football field as a table (bear DCF, base DCF, bull DCF, each multiple method, analyst range, 52w range).
4. Three bull points, three bear points, key catalysts.
5. If the user holds it: position-specific action.
6. Sources list.

Chat also gets the council line: Week / 3 mo / Year lean with seat agreement, and the priced-in score.

**Full deep dive:** the Council report built in 2b, at `equity/reports/<TICKER>-<YYYY-MM-DD>.html`,
published as an Artifact. Re-runs of the same ticker on the same day update the same file path.

Also save the engine inputs/outputs next to the report (`<TICKER>-<date>-inputs.json`, `-valuation.json`)
so assumptions are auditable.

Disclaimer line at the bottom: analysis, not personalised financial advice.
