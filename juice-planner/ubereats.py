#!/usr/bin/env python3
"""Work out how much Uber Eats adds to each shop's juice sales.

Reads Uber Eats Manager payment-detail exports (the per-item CSVs), compares them
with Square sales for the same dates, and prints the `uber_eats_pct` block for
config.json. Wellness Kits are opened into bottles on both sides.

  python3 ubereats.py --square sample-history.csv uber-sep.csv uber-oct.csv
  python3 ubereats.py --square sample-history.csv --write-csv uber-history.csv uber-*.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import planner

HERE = Path(__file__).resolve().parent
STORES = {"The Daily Beet (Magazine St)": "Magazine", "The Daily Beet (Girod St)": "Girod Street"}


def read_uber(paths: list[str], items: set[str]) -> list[tuple[date, str, str, float]]:
    canon = {i.lower(): i for i in items}
    rows = []
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows += list(csv.DictReader(f))
    # Item rows carry no store name; the order's header row does, linked by Workflow ID.
    store = {r["Workflow ID"]: r["Store Name"] for r in rows if r["Store Name"] and r["Workflow ID"]}
    totals: dict[tuple[date, str, str], float] = defaultdict(float)
    for r in rows:
        item = canon.get(r["Item Name"].strip().lower())
        loc = STORES.get(store.get(r["Workflow ID"], ""))
        if not item or not loc or r["Order Status"] != "Completed":
            continue
        d = datetime.strptime(r["Order Date"], "%m/%d/%y").date()
        totals[(d, loc, item)] += float(r["Final Quantity"] or 0)
    return [(d, loc, item, q) for (d, loc, item), q in sorted(totals.items())]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exports", nargs="+", help="Uber Eats CSV exports")
    ap.add_argument("--square", required=True, help="Square history CSV (date,location,item,qty)")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--write-csv", help="Also save Uber juice sales as date,location,item,qty")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    uber = read_uber(args.exports, set(cfg["recipes"]) | set(cfg["kits"]))
    square = planner.load_history_csv([args.square])
    lo = max(min(r[0] for r in uber), min(r[0] for r in square))
    hi = min(max(r[0] for r in uber), max(r[0] for r in square))

    def bottles(rows):
        daily = planner.bottles_by_day(cfg, [r for r in rows if lo <= r[0] <= hi])
        return {loc: {j: sum(s.values()) for j, s in js.items()} for loc, js in daily.items()}

    u, s = bottles(uber), bottles(square)
    pct = {loc: {j: round(100 * u[loc][j] / s[loc][j]) if s[loc][j] else 0 for j in cfg["juice_order"]} for loc in u}
    print(f"Compared {lo} to {hi}")
    for loc in pct:
        for j in cfg["juice_order"]:
            print(f"  {loc:13} {j:12} Uber {u[loc][j]:6.1f}  Square {s[loc][j]:6.1f}  +{pct[loc][j]}%")
    print(json.dumps({"uber_eats_pct": pct}, indent=2))

    if args.write_csv:
        with open(args.write_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "location", "item", "qty"])
            w.writerows(uber)


if __name__ == "__main__":
    main()
