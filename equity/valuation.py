"""Valuation engine for stock deep-dives.

Usage: python3 -I /home/user/equity/valuation.py <inputs.json>
Prints DCF (3 scenarios), WACC build, reverse DCF, sensitivity grid,
relative valuation and a blended fair value with rating as JSON.

inputs.json fields (USD millions unless noted, per-share in USD):
  ticker, price, shares_diluted, net_debt (debt + leases - cash; negative = net cash),
  minority_interest (opt), tax_rate, rf, erp, beta, pre_tax_cost_of_debt,
  debt_weight (target D/(D+E)),
  base_revenue, base_fcf_margin (opt, for reverse DCF),
  scenarios: {bear|base|bull: {growth: [g1..g5], fcf_margin: [m1..m5],
              terminal_growth, prob}},
  peers: [{ticker, pe_fwd, ev_ebitda_fwd, ev_sales_fwd, p_fcf, peg (opt)}],
  subject_metrics: {eps_fwd, ebitda_fwd, sales_fwd, fcf_per_share},
  weights (opt): {dcf: 0.5, multiples: 0.5}, dps (opt, next-12m dividend per share)

The rating uses the 12-month target: today's blended fair value rolled forward one year
at the cost of equity, less the dividend paid. Fair value alone is shown as intrinsic value.
"""
import json
import statistics
import sys


def wacc(i):
    ke = i["rf"] + i["beta"] * i["erp"]
    kd = i["pre_tax_cost_of_debt"] * (1 - i["tax_rate"])
    wd = i["debt_weight"]
    return ke * (1 - wd) + kd * wd, ke, kd


def dcf(i, sc, r, g_term=None):
    rev = i["base_revenue"]
    pv = 0.0
    fcf = 0.0
    for t, (g, m) in enumerate(zip(sc["growth"], sc["fcf_margin"]), start=1):
        rev *= 1 + g
        fcf = rev * m
        pv += fcf / (1 + r) ** (t - 0.5)  # mid-year convention
    n = len(sc["growth"])
    gt = sc["terminal_growth"] if g_term is None else g_term
    tv = fcf * (1 + gt) / (r - gt)
    pv_tv = tv / (1 + r) ** n
    ev = pv + pv_tv
    equity = ev - i["net_debt"] - i.get("minority_interest", 0)
    return {
        "ev": ev,
        "equity": equity,
        "per_share": equity / i["shares_diluted"],
        "tv_share_of_ev": pv_tv / ev,
        "final_rev": rev,
        "final_fcf": fcf,
    }


def reverse_dcf(i, r):
    """Constant 5y revenue CAGR the market price implies at base terminal assumptions."""
    base = i["scenarios"]["base"]
    m = i.get("base_fcf_margin", base["fcf_margin"][-1])
    lo, hi = -0.5, 1.5
    for _ in range(200):
        mid = (lo + hi) / 2
        sc = {"growth": [mid] * 5, "fcf_margin": [m] * 5,
              "terminal_growth": base["terminal_growth"]}
        if dcf(i, sc, r)["per_share"] > i["price"]:
            hi = mid
        else:
            lo = mid
    return mid


def multiples(i):
    s = i["subject_metrics"]
    p = i["peers"]
    out = {}
    nd = i["net_debt"] + i.get("minority_interest", 0)
    sh = i["shares_diluted"]

    def med(k):
        v = [x[k] for x in p if x.get(k) is not None]
        return statistics.median(v) if v else None

    if med("pe_fwd") and s.get("eps_fwd"):
        out["P/E fwd"] = {"peer_median": med("pe_fwd"), "implied": med("pe_fwd") * s["eps_fwd"]}
    if med("ev_ebitda_fwd") and s.get("ebitda_fwd"):
        m = med("ev_ebitda_fwd")
        out["EV/EBITDA fwd"] = {"peer_median": m, "implied": (m * s["ebitda_fwd"] - nd) / sh}
    if med("ev_sales_fwd") and s.get("sales_fwd"):
        m = med("ev_sales_fwd")
        out["EV/Sales fwd"] = {"peer_median": m, "implied": (m * s["sales_fwd"] - nd) / sh}
    if med("p_fcf") and s.get("fcf_per_share"):
        out["P/FCF"] = {"peer_median": med("p_fcf"), "implied": med("p_fcf") * s["fcf_per_share"]}
    return out


def rating(upside):
    if upside >= 0.15:
        return "BUY"
    if upside <= -0.10:
        return "SELL"
    return "HOLD"


def main(path):
    i = json.load(open(path))
    r, ke, kd = wacc(i)
    scen = {k: dcf(i, v, r) for k, v in i["scenarios"].items()}
    prob_dcf = sum(scen[k]["per_share"] * i["scenarios"][k]["prob"] for k in scen)

    base = i["scenarios"]["base"]
    grid = {}
    for dr in (-0.01, -0.005, 0, 0.005, 0.01):
        row = {}
        for dg in (-0.01, -0.005, 0, 0.005, 0.01):
            row[f"g={base['terminal_growth'] + dg:.3f}"] = round(
                dcf(i, base, r + dr, base["terminal_growth"] + dg)["per_share"], 2)
        grid[f"wacc={r + dr:.3f}"] = row

    mult = multiples(i)
    mult_val = statistics.median([v["implied"] for v in mult.values()]) if mult else None
    w = i.get("weights", {"dcf": 0.5, "multiples": 0.5})
    blended = prob_dcf if mult_val is None else w["dcf"] * prob_dcf + w["multiples"] * mult_val
    upside = blended / i["price"] - 1
    target = blended * (1 + ke) - i.get("dps", 0)
    t_up = target / i["price"] - 1

    print(json.dumps({
        "ticker": i["ticker"],
        "price": i["price"],
        "wacc": round(r, 4), "cost_of_equity": round(ke, 4), "after_tax_cost_of_debt": round(kd, 4),
        "dcf": {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in scen.items()},
        "prob_weighted_dcf": round(prob_dcf, 2),
        "reverse_dcf_implied_5y_rev_cagr": round(reverse_dcf(i, r), 4),
        "sensitivity_base_per_share": grid,
        "multiples": mult,
        "multiples_fair_value": None if mult_val is None else round(mult_val, 2),
        "blended_fair_value": round(blended, 2),
        "upside": round(upside, 4),
        "target_12m": round(target, 2),
        "target_upside": round(t_up, 4),
        "rating": rating(t_up),
    }, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
