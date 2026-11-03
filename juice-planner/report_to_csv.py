#!/usr/bin/env python3
"""Convert a Square Reporting API ItemSales response (daily items_sold_count by
item_name and location_name) into the planner's date,location,item,qty CSV.

  python3 report_to_csv.py response.json square-history.csv
"""

import csv
import json
import sys


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]
    data = json.load(open(src))["data"]
    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "location", "item", "qty"])
        for r in sorted(data, key=lambda r: r["ItemSales.reporting_day.day"]):
            w.writerow([
                r["ItemSales.reporting_day.day"][:10],
                r["ItemSales.location_name"],
                r["ItemSales.item_name"],
                r["ItemSales.items_sold_count"],
            ])
    print(f"{len(data)} rows -> {dst}")


if __name__ == "__main__":
    main()
