"""Generate a realistic, deliberately dirty retail orders CSV.

No real dataset ships with the repo, so this script creates one. A few percent
of the rows contain injected problems (duplicates, missing keys, bad dates,
negative quantities, ...) so the validation layer has real work to do. To use
your own data instead, drop a CSV with the same columns into data/raw/.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from etl.config import RAW_COLUMNS, RAW_DIR

CITIES = [
    ("Mumbai", "India"), ("Delhi", "India"), ("Bengaluru", "India"),
    ("Surat", "India"), ("Ahmedabad", "India"), ("Hyderabad", "India"),
    ("London", "UK"), ("Manchester", "UK"), ("New York", "USA"),
    ("Austin", "USA"), ("Berlin", "Germany"), ("Dubai", "UAE"),
]
CATEGORIES = {
    "Electronics": (800, 60000), "Home": (150, 15000), "Books": (80, 1500),
    "Fashion": (300, 6000), "Sports": (250, 9000), "Grocery": (20, 800),
}
PAYMENTS = ["card", "upi", "cod", "wallet", "netbanking"]


def generate(rows: int, seed: int, start: str, days: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    n_customers, n_products = 2000, 150
    cust_idx = np.arange(1, n_customers + 1)
    city_pick = rng.integers(0, len(CITIES), n_customers)
    customers = pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in cust_idx],
        "customer_name": [f"Customer {i}" for i in cust_idx],
        "email": [f"customer{i}@example.com" for i in cust_idx],
        "city": [CITIES[i][0] for i in city_pick],
        "country": [CITIES[i][1] for i in city_pick],
    })

    cat_names = list(CATEGORIES)
    cat_pick = rng.integers(0, len(cat_names), n_products)
    prices = [round(float(rng.uniform(*CATEGORIES[cat_names[c]])), 2) for c in cat_pick]
    products = pd.DataFrame({
        "product_id": [f"P{i:04d}" for i in range(1, n_products + 1)],
        "product_name": [f"Product {i}" for i in range(1, n_products + 1)],
        "category": [cat_names[c] for c in cat_pick],
        "unit_price": prices,
    })

    # Orders have 1-4 lines each; trim to exactly `rows` lines.
    lines_per_order = rng.integers(1, 5, size=rows)
    order_ids = np.repeat(np.arange(1, rows + 1), lines_per_order)[:rows]
    line_no = pd.Series(order_ids).groupby(order_ids).cumcount().to_numpy() + 1
    n_orders = int(order_ids.max())
    order_customer = rng.integers(0, n_customers, n_orders + 1)
    order_day = rng.integers(0, days, n_orders + 1)
    order_pay = rng.choice(PAYMENTS, n_orders + 1)

    base = pd.Timestamp(start)
    df = customers.iloc[order_customer[order_ids]].reset_index(drop=True)
    prod = products.iloc[rng.integers(0, n_products, rows)].reset_index(drop=True)
    df = pd.concat([df, prod], axis=1)
    df["order_id"] = [f"O{o:07d}" for o in order_ids]
    df["order_line"] = line_no
    dates = base + pd.to_timedelta(order_day[order_ids], unit="D")
    df["order_date"] = dates.strftime("%Y-%m-%d")
    df["quantity"] = rng.integers(1, 6, rows)
    df["discount"] = rng.choice([0, 0, 0, 0.05, 0.1, 0.2], rows)
    df["payment_method"] = order_pay[order_ids]
    df = df[RAW_COLUMNS].astype(object)

    # ---- inject problems -------------------------------------------------
    def pick(frac):
        return rng.random(rows) < frac

    df.loc[pick(0.010), "customer_id"] = None            # missing key
    df.loc[pick(0.010), "quantity"] = -1                  # negative qty
    df.loc[pick(0.005), "quantity"] = 0
    df.loc[pick(0.010), "order_date"] = "31/02/2026"      # unparseable date
    df.loc[pick(0.005), "order_date"] = "2099-01-01"      # future date
    df.loc[pick(0.005), "unit_price"] = -10               # bad price
    df.loc[pick(0.005), "discount"] = 1.5                 # impossible discount
    df.loc[pick(0.020), "email"] = "not-an-email"         # fixable: nulled
    mess = pick(0.05)                                     # fixable: standardised
    df.loc[mess, "city"] = df.loc[mess, "city"].map(lambda c: f"  {str(c).upper()} ")
    df.loc[pick(0.010), "country"] = None                 # fixable: 'Unknown'

    dupes = df.sample(frac=0.02, random_state=seed)       # exact duplicate rows
    df = pd.concat([df, dupes], ignore_index=True)
    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rows", type=int, default=100_000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--start", default="2026-01-01")
    p.add_argument("--days", type=int, default=300)
    p.add_argument("--out", type=Path, default=RAW_DIR / "orders_raw.csv")
    a = p.parse_args()

    a.out.parent.mkdir(parents=True, exist_ok=True)
    df = generate(a.rows, a.seed, a.start, a.days)
    df.to_csv(a.out, index=False)
    print(f"Wrote {len(df):,} rows to {a.out}")


if __name__ == "__main__":
    main()
