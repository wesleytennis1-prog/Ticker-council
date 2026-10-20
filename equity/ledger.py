"""Call ledger: records every council call and scores it once its horizon has passed.

  python3 -I ledger.py add <report.data.json>         append the call (append-only)
  python3 -I ledger.py due [YYYY-MM-DD]               list horizons ready to score
  python3 -I ledger.py score <id> <horizon> <price>   record the realised price
  python3 -I ledger.py stats                          hit rates per seat/horizon -> calibration.json

A direction is a hit when the realised move has the called sign, or when the call was
"even" and the move stayed within half a sigma. Seats that hit more often get more weight.
"""
import json
import math
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "ledger.jsonl"


def rows():
    return [json.loads(l) for l in LEDGER.read_text().splitlines() if l] if LEDGER.exists() else []


def write(rs):
    LEDGER.write_text("".join(json.dumps(r) + "\n" for r in rs))


def add(path):
    d = json.loads(Path(path).read_text())
    m = d["meta"]
    rec = {"id": f"{m['ticker']}-{m['asof'][:10]}", "ticker": m["ticker"], "asof": m["asof"][:10],
           "price": m["price"], "rating": d["call"]["rating"], "target": d["call"].get("target"),
           "council": {c["key"]: {"score": c["score"], "lean": c["lean"]} for c in d["council"]},
           "fans": d["price"]["fans"],
           "seats": {s["name"]: {k: v["vote"] for k, v in s["votes"].items()} for s in d["seats"]},
           "results": {}}
    rs = [r for r in rows() if r["id"] != rec["id"]]
    write(rs + [rec])
    print("recorded", rec["id"])


def hit(called, ret, sigma):
    if called == "even":
        return abs(ret) < 0.5 * sigma
    return (ret > 0) == (called == "up")


def due(today):
    for r in rows():
        for h, f in r["fans"].items():
            if f["date"] <= today and h not in r["results"]:
                print(r["id"], h, f["date"])


def score(rid, h, price):
    rs = rows()
    for r in rs:
        if r["id"] == rid:
            ret = math.log(price / r["price"])
            sig = r["fans"][h]["sigma"]
            lean = r["council"][h]["lean"].lower()
            called = "up" if "up" in lean else "down" if "down" in lean else "even"
            f = r["fans"][h]
            r["results"][h] = {"price": price, "ret": round(ret, 4), "council_hit": hit(called, ret, sig),
                               "in_band": f["lo"] <= price <= f["hi"],
                               "seat_hits": {n: hit(v[h], ret, sig) for n, v in r["seats"].items()}}
            print(rid, h, r["results"][h])
    write(rs)


def stats():
    tally = {}
    for r in rows():
        for h, res in r["results"].items():
            for n, ok in res["seat_hits"].items():
                t = tally.setdefault(n, {}).setdefault(h, [0, 0])
                t[0] += ok
                t[1] += 1
    # Shrink towards 50% with 10 pseudo-calls so a handful of results can't swing weights.
    # Weight = 2 x shrunk hit rate, so a coin-flip seat keeps weight 1.0.
    calib = {n: {h: round(max(0.3, min(1.7, 2 * (k + 5) / (m + 10))), 3) for h, (k, m) in hs.items()}
             for n, hs in tally.items()}
    (HERE / "calibration.json").write_text(json.dumps(calib, indent=1))
    print(json.dumps({"tally": tally, "weights": calib}, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "add":
        add(sys.argv[2])
    elif cmd == "due":
        due(sys.argv[2] if len(sys.argv) > 2 else date.today().isoformat())
    elif cmd == "score":
        score(sys.argv[2], sys.argv[3], float(sys.argv[4]))
    elif cmd == "stats":
        stats()
