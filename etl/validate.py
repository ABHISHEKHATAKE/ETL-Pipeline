"""Validate: split cleaned rows into valid and rejected, with a reason per reject."""
import json
import logging

import numpy as np
import pandas as pd

from etl.config import MAX_REJECT_RATE

log = logging.getLogger(__name__)


class DataQualityError(Exception):
    """Raised when too many rows fail validation to trust the batch."""


# Order matters: a row is tagged with the FIRST rule it breaks.
def _rules(today: pd.Timestamp):
    return [
        ("missing_order_id",   lambda d: d["order_id"].isna() | d["order_line"].isna()),
        ("missing_customer_id", lambda d: d["customer_id"].isna()),
        ("missing_product_id",  lambda d: d["product_id"].isna()),
        ("invalid_order_date",  lambda d: d["order_date"].isna()),
        ("future_order_date",   lambda d: d["order_date"] > today),
        ("invalid_quantity",    lambda d: d["quantity"].isna() | (d["quantity"] <= 0)),
        ("invalid_unit_price",  lambda d: d["unit_price"].isna() | (d["unit_price"] <= 0)),
        ("invalid_discount",    lambda d: (d["discount"] < 0) | (d["discount"] > 1)),
    ]


def validate(clean: pd.DataFrame, raw: pd.DataFrame, today: pd.Timestamp | None = None):
    """Return (valid_df, rejected_df).

    `raw` is the untouched extract (same index as `clean`); it supplies the original
    values stored in the rejected-records audit table.
    """
    today = (today or pd.Timestamp.today()).normalize()
    reason = np.full(len(clean), None, dtype=object)

    for name, rule in _rules(today):
        mask = np.asarray(rule(clean).fillna(False), dtype=bool) & (reason == None)  # noqa: E711
        reason[mask] = name

    # Duplicates are only judged among rows that passed every other rule, so a bad
    # first copy never hides a good second copy. The first occurrence wins.
    ok = reason == None  # noqa: E711
    dup = np.zeros(len(clean), dtype=bool)
    dup[ok] = clean.loc[ok].duplicated(subset=["order_id", "order_line"], keep="first").to_numpy()
    reason[dup] = "duplicate_order_line"

    ok = reason == None  # noqa: E711
    valid = clean.loc[ok].copy()

    bad_idx = clean.index[~ok]
    rejected = pd.DataFrame({
        "reject_reason": reason[~ok],
        "source_file": raw.loc[bad_idx, "source_file"].to_numpy(),
        "payload": [
            json.dumps({k: (None if pd.isna(v) else v) for k, v in row.items()})
            for row in raw.loc[bad_idx].drop(columns=["source_file"]).to_dict("records")
        ],
    }, index=bad_idx)

    log.info("Validation: %s valid, %s rejected", f"{len(valid):,}", f"{len(rejected):,}")
    for r, n in rejected["reject_reason"].value_counts().items():
        log.info("  %-22s %s", r, f"{n:,}")
    return valid, rejected


def quality_gate(total_rows: int, rejected_rows: int, max_rate: float = MAX_REJECT_RATE) -> float:
    """Fail the run before loading if the reject rate is suspiciously high."""
    rate = rejected_rows / total_rows if total_rows else 1.0
    if rate > max_rate:
        raise DataQualityError(
            f"Reject rate {rate:.1%} exceeds the {max_rate:.0%} threshold; nothing was loaded."
        )
    return rate
