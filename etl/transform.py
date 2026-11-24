"""Transform: standardise and type the raw data, then build star-schema frames."""
import re

import numpy as np
import pandas as pd

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TEXT_COLS = [
    "order_id", "customer_id", "customer_name", "email", "city", "country",
    "product_id", "product_name", "category", "payment_method",
]


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Standardise text, parse types. Does NOT drop rows: bad values become NaN/NaT
    and are judged by the validation step. The index is preserved so rejected rows
    can be traced back to the raw frame."""
    df = raw.copy()

    for col in TEXT_COLS:
        df[col] = df[col].astype("object").map(
            lambda v: v.strip() if isinstance(v, str) else v
        )
        df[col] = df[col].map(lambda v: None if v == "" else v)

    # Keys are upper-cased so 'c00001' and 'C00001' are the same customer.
    for col in ("order_id", "customer_id", "product_id"):
        df[col] = df[col].map(lambda v: v.upper() if isinstance(v, str) else v)

    df["customer_name"] = df["customer_name"].map(lambda v: v.title() if isinstance(v, str) else v)
    df["city"] = df["city"].map(lambda v: v.title() if isinstance(v, str) else v)
    df["category"] = df["category"].map(lambda v: v.title() if isinstance(v, str) else v)
    df["payment_method"] = df["payment_method"].map(lambda v: v.lower() if isinstance(v, str) else v)
    df["country"] = df["country"].map(lambda v: v if isinstance(v, str) else "Unknown")

    # Malformed e-mail is a fixable problem: keep the row, drop the bad value.
    df["email"] = df["email"].map(
        lambda v: v.lower() if isinstance(v, str) and EMAIL_RE.match(v) else None
    )

    df["order_date"] = pd.to_datetime(df["order_date"], format="%Y-%m-%d", errors="coerce")
    df["order_line"] = pd.to_numeric(df["order_line"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["discount"] = pd.to_numeric(df["discount"], errors="coerce").fillna(0.0)
    return df


def add_metrics(valid: pd.DataFrame) -> pd.DataFrame:
    df = valid.copy()
    df["gross_amount"] = (df["quantity"] * df["unit_price"]).round(2)
    df["net_amount"] = (df["gross_amount"] * (1 - df["discount"])).round(2)
    df["date_key"] = df["order_date"].dt.strftime("%Y%m%d").astype(int)
    return df


def build_dim_customer(df: pd.DataFrame) -> pd.DataFrame:
    """One row per customer, keeping the most recent attributes (SCD type 1)."""
    cols = ["customer_id", "customer_name", "email", "city", "country"]
    return (
        df.sort_values("order_date")
        .drop_duplicates("customer_id", keep="last")[cols]
        .reset_index(drop=True)
    )


def build_dim_product(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["product_id", "product_name", "category", "unit_price"]
    out = (
        df.sort_values("order_date")
        .drop_duplicates("product_id", keep="last")[cols]
        .rename(columns={"unit_price": "list_price"})
        .reset_index(drop=True)
    )
    return out


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame({
        "date_key": days.strftime("%Y%m%d").astype(int),
        "full_date": days.date,
        "year": days.year,
        "quarter": days.quarter,
        "month": days.month,
        "month_name": days.strftime("%B"),
        "day": days.day,
        "day_of_week": days.dayofweek + 1,
        "day_name": days.strftime("%A"),
        "is_weekend": np.asarray(days.dayofweek >= 5),
    })
