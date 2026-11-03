#!/usr/bin/env python3
"""Juice planner for The Daily Beet.

Pulls recent juice sales from Square, forecasts demand for the next juicing
window (Monday covers Mon-Thu, Friday covers Fri-Sun), and writes a prep page
the juicer opens in the morning. The page asks for bottles still in the
cooler, then shows bottles to press and produce weights.

Usage:
  SQUARE_ACCESS_TOKEN=... python3 planner.py --out site/index.html
  python3 planner.py --history-csv sample-history.csv --date 2026-11-06

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SQUARE_URL = "https://connect.squareup.com/v2/orders/search"
SQUARE_VERSION = "2025-01-23"


# ---------------------------------------------------------------- schedule

def juice_weekdays(cfg) -> list[int]:
    return sorted(WEEKDAYS.index(d) for d in cfg["juice_days"])


def next_juice_day(cfg, today: date) -> date:
    days = juice_weekdays(cfg)
    for i in range(7):
        d = today + timedelta(days=i)
        if d.weekday() in days:
            return d
    raise ValueError("juice_days is empty")


def window_for(cfg, juice_day: date) -> list[date]:
    """Dates this batch has to cover: juice day up to the day before the next one."""
    days = juice_weekdays(cfg)
    out = [juice_day]
    d = juice_day + timedelta(days=1)
    while d.weekday() not in days:
        out.append(d)
        d += timedelta(days=1)
    return out


def previous_juice_day(cfg, juice_day: date) -> date:
    days = juice_weekdays(cfg)
    d = juice_day - timedelta(days=1)
    while d.weekday() not in days:
        d -= timedelta(days=1)
    return d


# ---------------------------------------------------------------- history

def load_history_csv(paths: list[str]) -> list[tuple[date, str, str, float]]:
    """CSV columns: date (YYYY-MM-DD), location, item, qty. Several files are summed,
    so an Uber Eats export reshaped to these columns can be added alongside Square."""
    rows = []
    for p in paths:
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                rows.append((date.fromisoformat(r["date"][:10]), r["location"], r["item"], float(r["qty"])))
    return rows


def fetch_square_history(cfg, token: str, start: date, end: date) -> list[tuple[date, str, str, float]]:
    """Completed orders between start and end (inclusive, local time), counted by line item."""
    tz = ZoneInfo(cfg["timezone"])
    wanted = set(cfg["recipes"]) | set(cfg["kits"])
    start_utc = datetime.combine(start, datetime.min.time(), tz).astimezone(ZoneInfo("UTC"))
    end_utc = datetime.combine(end + timedelta(days=1), datetime.min.time(), tz).astimezone(ZoneInfo("UTC"))
    body = {
        "location_ids": list(cfg["locations"]),
        "limit": 500,
        "query": {
            "filter": {
                "state_filter": {"states": ["COMPLETED"]},
                "date_time_filter": {"closed_at": {
                    "start_at": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end_at": end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }},
            },
            "sort": {"sort_field": "CLOSED_AT", "sort_order": "ASC"},
        },
    }
    totals: dict[tuple[date, str, str], float] = defaultdict(float)
    pages = 0
    while True:
        req = urllib.request.Request(
            SQUARE_URL,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Square-Version": SQUARE_VERSION,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        pages += 1
        for order in data.get("orders", []):
            loc = cfg["locations"].get(order["location_id"])
            if not loc:
                continue
            day = datetime.fromisoformat(order["closed_at"].replace("Z", "+00:00")).astimezone(tz).date()
            for li in order.get("line_items", []):
                if li.get("name") in wanted:
                    totals[(day, loc, li["name"])] += float(li.get("quantity", 0))
        cursor = data.get("cursor")
        if not cursor:
            break
        body["cursor"] = cursor
    print(f"Read {pages} page(s) of Square orders", file=sys.stderr)
    return [(d, loc, item, q) for (d, loc, item), q in totals.items()]


# ---------------------------------------------------------------- forecast

def bottles_by_day(cfg, rows) -> dict[str, dict[str, dict[date, float]]]:
    """Turn item sales into bottles of each juice per location per day, opening kits."""
    juices = list(cfg["recipes"])
    out = {loc: {j: defaultdict(float) for j in juices} for loc in cfg["locations"].values()}
    kits = defaultdict(lambda: defaultdict(float))  # loc -> date -> kit bottles to split
    for d, loc, item, q in rows:
        if loc not in out:
            continue
        if item in out[loc]:
            out[loc][item][d] += q
        elif item in cfg["kits"]:
            kit = cfg["kits"][item]
            for juice, n in kit.items():
                if juice in out[loc]:
                    out[loc][juice][d] += q * n
            kits[(loc, item)][d] += q
    # A kit's greens are the customer's pick, which Square doesn't record,
    # so split them in proportion to how each greens juice sells at that shop.
    for (loc, item), days in kits.items():
        choice = cfg["kits"][item].get("greens_choice", [])
        sold = {j: sum(out[loc][j].values()) for j in choice}
        total = sum(sold.values()) or 1
        for d, q in days.items():
            for j in choice:
                out[loc][j][d] += q * sold[j] / total
    return out


def forecast_day(cfg, series: dict[date, float], target: date, last_day: date) -> float:
    """Weighted average of the same weekday over recent weeks (most recent weighted most)."""
    weights = cfg["recency_weights"][: cfg["history_weeks"]]
    d = target - timedelta(days=7)
    while d > last_day:
        d -= timedelta(days=7)
    num = den = 0.0
    for w in weights:
        num += w * series.get(d, 0.0)
        den += w
        d -= timedelta(days=7)
    return num / den if den else 0.0


def build_plan(cfg, rows, juice_day: date, last_day: date) -> dict:
    window = window_for(cfg, juice_day)
    prev = previous_juice_day(cfg, juice_day)
    daily = bottles_by_day(cfg, rows)
    forecast = {
        loc: {
            j: {d.isoformat(): round(forecast_day(cfg, series, d, last_day), 2) for d in window}
            for j, series in juices.items()
        }
        for loc, juices in daily.items()
    }
    return {
        "generated_at": datetime.now(ZoneInfo(cfg["timezone"])).strftime("%Y-%m-%d %H:%M"),
        "juice_day": juice_day.isoformat(),
        "window": [d.isoformat() for d in window],
        "previous_juice_day": prev.isoformat(),
        "history_through": last_day.isoformat(),
        "history_weeks": cfg["history_weeks"],
        "bottle_oz": cfg["bottle_oz"],
        "shelf_life_days": cfg["shelf_life_days"],
        "buffer_pct": cfg["buffer_pct"],
        "uber_eats_pct": cfg["uber_eats_pct"],
        "locations": list(cfg["locations"].values()),
        "juice_order": cfg["juice_order"],
        "recipes": cfg["recipes"],
        "forecast": forecast,
    }


def render(plan: dict, template: Path, out: Path) -> None:
    html = template.read_text().replace("__PLAN_DATA__", json.dumps(plan, separators=(",", ":")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--template", default=str(HERE / "template.html"))
    ap.add_argument("--out", default=str(HERE / "site" / "index.html"))
    ap.add_argument("--date", help="Plan for the next juice day on or after this date (default: tomorrow)")
    ap.add_argument("--history-csv", action="append", default=[],
                    help="Use sales from CSV instead of, or as well as, Square (repeatable)")
    ap.add_argument("--json", action="store_true", help="Also print the plan data")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    tz = ZoneInfo(cfg["timezone"])
    start_from = date.fromisoformat(args.date) if args.date else datetime.now(tz).date() + timedelta(days=1)
    juice_day = next_juice_day(cfg, start_from)
    last_day = juice_day - timedelta(days=1)

    rows = load_history_csv(args.history_csv)
    token = os.environ.get("SQUARE_ACCESS_TOKEN")
    if token:
        first = last_day - timedelta(weeks=cfg["history_weeks"]) + timedelta(days=1)
        rows += fetch_square_history(cfg, token, first, last_day)
    elif not rows:
        sys.exit("Set SQUARE_ACCESS_TOKEN or pass --history-csv")
    if args.history_csv and not token:
        last_day = min(last_day, max(r[0] for r in rows))

    plan = build_plan(cfg, rows, juice_day, last_day)
    render(plan, Path(args.template), Path(args.out))
    if args.json:
        print(json.dumps(plan, indent=2))
    print(f"Plan for {juice_day:%A %b %-d} written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
