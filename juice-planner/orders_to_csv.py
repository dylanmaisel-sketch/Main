#!/usr/bin/env python3
"""Add one day's juice sales from a Square Orders search response to the history CSV.

Square's reporting data lags same-day sales, so the nightly refresh reads today's
completed orders directly and appends them here.

  python3 orders_to_csv.py orders.json sample-history.csv 2026-11-08
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    src, dst, day = sys.argv[1], sys.argv[2], sys.argv[3]
    cfg = json.loads((HERE / "config.json").read_text())
    wanted = set(cfg["recipes"]) | set(cfg["kits"])
    data = json.load(open(src))
    if data.get("cursor"):
        sys.exit("Orders response has more pages; fetch them all before running this.")
    counts = Counter()
    for order in data.get("orders", []):
        loc = cfg["locations"].get(order["location_id"])
        for li in order.get("line_items", []):
            if loc and li.get("name") in wanted:
                counts[(loc, li["name"])] += float(li.get("quantity", 0))
    with open(dst, newline="") as f:
        rows = [r for r in csv.reader(f)]
    header, body = rows[0], [r for r in rows[1:] if r[0] != day]
    body += [[day, loc, item, q] for (loc, item), q in sorted(counts.items())]
    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    print(f"{len(data.get('orders', []))} orders, {len(counts)} juice rows for {day} -> {dst}")


if __name__ == "__main__":
    main()
