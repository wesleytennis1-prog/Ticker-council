# Workspace: equity deep-dives

When the user's message is just a ticker symbol (or "deep dive X"), run the `stock-deep-dive` skill
(`.claude/skills/stock-deep-dive/SKILL.md`). Valuation engine: `equity/valuation.py`. Reports: `equity/reports/`.
Data: IBKR connector first for prices and the user's positions; web for fundamentals, filings and consensus.

All paths are relative to the repository root; run commands from there.
After every ticker run, commit the new report, its data/inputs JSON, `equity/ledger.jsonl` and
`equity/calibration.json`, and push to the repository's default branch, so the call history survives the session.
