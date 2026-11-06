# Juice planner

Tells the juicer how many bottles of **Pure Greens, NOLA Greens and Roots** to press on each juice day, and how much produce to weigh out. It covers **Magazine** and **Girod Street**.

## What the juicer does

1. Open the juice plan page on the morning of a juice day (Monday or Friday).
2. Count the bottles left in each cooler from the last juice day and enter them.
3. Press the bottle counts shown. Then weigh out the produce list, which follows the X-1 run order: ginger, Pure Greens, NOLA Greens, rinse, Roots.

## How it decides

- **Window.** Monday's batch covers Mon–Thu. Friday's covers Fri–Sun. Bottles have a 5-day shelf life (made Monday, good through Friday).
- **Forecast.** For each shop, juice and day, it averages the same weekday over the last 6 weeks of completed Square orders. Recent weeks count more (weights 3,3,2,2,1,1). In-store, kiosk and online orders are all included.
- **Wellness Kits.** Each kit counts as one Roots plus one greens. Square doesn't record which greens the customer picks, so the greens are split by how NOLA and Pure sell at that shop.
- **Buffer.** It adds 10% (`buffer_pct`).
- **Leftovers.** The juicer counts only bottles that don't expire by tomorrow, since anything expiring today or tomorrow is likely to go to waste. Counted bottles are subtracted, credited against sales through the day after tomorrow.
- **Produce.** Weights are raised by `yield_pct` where the press gives less juice than the recipe sheet says (Roots: 71%, from 16 qt made vs 22.5 qt expected on Nov 6, 2026). Otherwise amounts match the recipe sheet exactly at its standard batch sizes (12/14 qt and 20 qt). Between and beyond those sizes they scale in a straight line. Weights round to ¼ lb. One bottle is 12 oz, so 8 bottles make 3 quarts.

All of these settings are in `config.json`.

## Uber Eats

Uber Eats orders don't reach Square, so the planner raises each shop's forecast by Uber's share. The shares are in `uber_eats_pct` in `config.json`. They were measured from Uber Eats payment-detail exports against Square for Sep 7 – Oct 31, 2026, with Wellness Kits opened into bottles:

| | Pure Greens | NOLA Greens | Roots |
|---|---|---|---|
| Magazine | +26% | +16% | +13% |
| Girod Street | +24% | +25% | +18% |

To refresh the shares every month or two, download the Uber Eats exports and run:

```bash
python3 ubereats.py --square sample-history.csv uber-export-1.csv uber-export-2.csv
```

Then paste the printed block into `config.json`. The Square history CSV must cover the same dates. `uber-history.csv` holds the daily Uber juice sales from the current exports.

If Uber Eats is ever connected to Square, set every value to `0`. Otherwise those orders are counted twice.

## Running it

```bash
# From Square (needs an access token with ORDERS_READ)
SQUARE_ACCESS_TOKEN=... python3 planner.py --out site/index.html

# Complete HTML document (for publishing tools that need a doctype)
SQUARE_ACCESS_TOKEN=... python3 planner.py --standalone --out site/index.html

# From a CSV of past sales
python3 planner.py --history-csv sample-history.csv --date 2026-11-06
```

`--date` plans for the next juice day on or after that date. The default is tomorrow, so a run on Sunday night builds Monday's plan. Only the Python 3.9+ standard library is needed.

`sample-history.csv` holds daily juice and Wellness Kit sales for Magazine and Girod Street, Sep 7 – Nov 1, 2026, from Square reporting.

## Automatic nightly build

`.github/workflows/juice-plan.yml` builds the page Sunday and Thursday nights and publishes it to GitHub Pages at `/juice/`. To turn it on:

1. Add a repository secret `SQUARE_ACCESS_TOKEN` (Settings → Secrets and variables → Actions). Use a production access token from the Square Developer Dashboard with `ORDERS_READ`.
2. Set Settings → Pages → Source to **GitHub Actions**.
3. Run the workflow once by hand (Actions → Juice plan → Run workflow) to check it.

If this repo's Pages site is used for something else, change the workflow's output path or publish it elsewhere.
