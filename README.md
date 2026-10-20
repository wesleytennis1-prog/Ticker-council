# Ticker Council

Single-stock deep dives run by Claude Code: type a ticker, get a full equity valuation, a
Buy/Hold/Sell call and a Council report (12 seats voting on week / 3 month / year, debate,
business check, price forecast fan, valuation and the books).

- `.claude/skills/stock-deep-dive/SKILL.md`: the playbook
- `equity/valuation.py`: DCF scenarios, reverse DCF, sensitivity, peer multiples, rating
- `equity/council.py` + `equity/template.html`: seat aggregation, forecast fan, priced-in score, HTML report
- `equity/ledger.py`: call log, scoring at each horizon, seat re-weighting (`ledger.jsonl`, `calibration.json`)
- `equity/reports/`: published reports

Analysis, not personalised financial advice.
