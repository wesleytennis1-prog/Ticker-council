"""Council engine: turns seat votes + valuation into the report data, then renders HTML.

Usage: python3 -I /home/user/equity/council.py <council_inputs.json> <valuation.json> <out.html>

council_inputs.json carries the researched content (meta, call, position, seats with
per-horizon scores in [-1, 1], debate, business metrics, price history, financials,
comps, risks, sources). This script adds the computed parts:
  - seat vote labels and the weighted council position per horizon
  - the price forecast fan (70% bands) per horizon
  - the priced-in score (0-100)
  - growth state
and writes report_data.json next to the HTML for the call ledger.
"""
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
HORIZONS = [("week", "Next week", "Scored in 7 days", 7, 5),
            ("m3", "Next 3 months", "Scored in 3 months", 91, 63),
            ("year", "Next year", "Scored in a year", 365, 252)]

# Default seat weights per horizon (week, m3, year). Fast-moving signals matter more
# short term; fundamentals matter more long term. Overridden by ledger calibration.
SEAT_WEIGHTS = {
    "Price Chart": (1.5, 1.0, 0.6), "Financials": (0.6, 1.0, 1.5),
    "Analyst Targets": (0.8, 1.0, 1.2), "Earnings Estimates": (0.8, 1.3, 1.2),
    "Insider Trades": (0.5, 0.8, 0.8), "Congress Trades": (0.3, 0.4, 0.4),
    "News": (1.3, 1.0, 0.6), "SEC Filings": (0.5, 0.7, 0.9),
    "Institutional Holdings": (0.6, 0.9, 1.0), "Options Market": (1.4, 1.0, 0.5),
    "Economy": (0.7, 0.9, 1.0), "Related Markets": (1.2, 1.0, 0.7),
}
Z70 = 1.036  # two-sided 70% interval of a normal
DRIFT_K = 0.6  # a unanimous "strongly up" moves the median by 0.6 sigma


def clamp01(x):
    return max(0.0, min(1.0, x))


def vote(score):
    return "up" if score > 0.15 else "down" if score < -0.15 else "even"


def lean(s):
    a, d = abs(s), ("up" if s > 0 else "down")
    rise = "rise" if s > 0 else "fall"
    if a < 0.08:
        return "Even", "Roughly a coin flip"
    if a < 0.2:
        return f"Leaning {d}", f"Slightly more likely to {rise}"
    if a < 0.4:
        return d.capitalize(), f"More likely to {rise}"
    return f"Strongly {d}", f"Much more likely to {rise}"


def load_calibration():
    p = HERE / "calibration.json"
    return json.loads(p.read_text()) if p.exists() else {}


def council(seats):
    calib = load_calibration()
    out = []
    for idx, (key, label, scored, _, _) in enumerate(HORIZONS):
        num = den = 0.0
        for s in seats:
            sc = s["votes"][key]["score"]
            w = SEAT_WEIGHTS.get(s["name"], (1, 1, 1))[idx] * calib.get(s["name"], {}).get(key, 1.0)
            num += w * sc
            den += w
        agg = num / den if den else 0.0
        # Same 0.08 threshold as lean(), so "Leaning down" counts the seats voting down.
        side = "up" if agg >= 0.08 else "down" if agg <= -0.08 else "even"
        agree = sum(1 for s in seats if s["votes"][key]["vote"] == side)
        text, sub = lean(agg)
        out.append({"key": key, "label": label, "scored": scored, "score": round(agg, 3),
                    "lean": text, "sub": sub, "agree": agree, "total": len(seats)})
    return out


def fans(price, sigma, council_pos, target, as_of):
    out = {}
    for (key, _, _, cal_days, td), c in zip(HORIZONS, council_pos):
        s = sigma * math.sqrt(td / 252)
        mid = target if key == "year" and target else price * math.exp(c["score"] * DRIFT_K * s)
        out[key] = {"date": (as_of + timedelta(days=cal_days)).isoformat(),
                    "lo": round(mid * math.exp(-Z70 * s), 2), "mid": round(mid, 2),
                    "hi": round(mid * math.exp(Z70 * s), 2), "sigma": round(s, 4)}
    return out


def priced_in(b, val):
    """0 = cheap vs what is expected, 100 = priced for perfection."""
    comps = []
    rows = []
    if b.get("peg") is not None:
        comps.append(clamp01((b["peg"] - 0.5) / 2.0))
        rows.append({"label": "Price vs expected growth (PEG)", "value": f"{b['peg']:.1f}x",
                     "state": "good" if b["peg"] < 1 else "warn" if b["peg"] < 2 else "bad"})
    implied = val.get("reverse_dcf_implied_5y_rev_cagr")
    if implied is not None and b.get("expected_growth"):
        r = implied / b["expected_growth"] if b["expected_growth"] > 0 else 3
        comps.append(clamp01((r - 0.5) / 1.5))
        rows.append({"label": "Growth the price assumes",
                     "value": f"~{implied:.0%}/yr vs ~{b['expected_growth']:.0%} expected",
                     "state": "good" if r < 0.9 else "warn" if r < 1.4 else "bad"})
    if b.get("price_chg_3m") is not None and b.get("eps_rev_3m") is not None:
        gap = b["price_chg_3m"] - b["eps_rev_3m"]
        comps.append(clamp01((gap + 0.2) / 0.6))
        rows.append({"label": "Price vs earnings estimates, 3 mo",
                     "value": f"{b['price_chg_3m']:+.0%} vs {b['eps_rev_3m']:+.0%}",
                     "state": "good" if gap < 0 else "warn" if gap < 0.15 else "bad"})
    if b.get("room_to_target") is not None:
        comps.append(clamp01((0.4 - b["room_to_target"]) / 0.5))
        rows.append({"label": "Room to analysts' average target", "value": f"{b['room_to_target']:+.0%}",
                     "state": "good" if b["room_to_target"] > 0.2 else "warn" if b["room_to_target"] > 0 else "bad"})
    if val.get("upside") is not None:
        comps.append(clamp01((0.3 - val["upside"]) / 0.6))
        rows.append({"label": "Room to our fair value", "value": f"{val['upside']:+.0%}",
                     "state": "good" if val["upside"] > 0.15 else "warn" if val["upside"] > -0.1 else "bad"})
    score = round(100 * sum(comps) / len(comps)) if comps else None
    if score is None:
        label = "n/a"
    else:
        label = ("Cheap" if score < 25 else "Partly" if score < 45 else "Fair" if score < 60
                 else "Mostly" if score < 80 else "Priced for perfection")
    return {"score": score, "label": label, "rows": rows}


def growth_state(bars):
    if len(bars) < 2:
        return "Steady"
    d = bars[-1]["value"] - bars[-2]["value"]
    return "Speeding up" if d > 0.03 else "Slowing" if d < -0.03 else "Steady"


def main(inp, valp, outp):
    d = json.loads(Path(inp).read_text())
    val = json.loads(Path(valp).read_text())
    as_of = date.fromisoformat(d["meta"]["asof"][:10])

    for s in d["seats"]:
        for k, v in s["votes"].items():
            v["vote"] = vote(v["score"])
    d["council"] = council(d["seats"])

    p = d["price"]
    p["fans"] = fans(d["meta"]["price"], p["sigma"], d["council"], d["call"].get("target"), as_of)
    p.setdefault("bull_price", val["dcf"]["bull"]["per_share"])
    p.setdefault("bear_price", val["dcf"]["bear"]["per_share"])

    b = d["business"]
    b["growth"]["state"] = growth_state(b["growth"]["bars"])
    b["priced_in"] = priced_in(b, val)
    d["valuation"] = val

    Path(outp).with_suffix(".data.json").write_text(json.dumps(d, indent=1))
    payload = json.dumps(d).replace("</", "<\\/")
    html = (HERE / "template.html").read_text().replace("__DATA__", payload)
    html = html.replace("__TITLE__", f"{d['meta']['ticker']} Council Report")
    Path(outp).write_text(html)
    print(json.dumps({"council": d["council"], "fans": p["fans"], "priced_in": b["priced_in"]}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
