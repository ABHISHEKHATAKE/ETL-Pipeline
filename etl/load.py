"""Load: idempotent upserts into the star schema, in ONE transaction.

Re-running the same data never creates duplicates: dimensions upsert on their
business key and the fact table upserts on (order_id, order_line). If anything
fails (including the reconciliation check) the whole load rolls back.
"""
import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from etl import transform
from etl.config import DATABASE_URL, SCHEMA_FILE

log = logging.getLogger(__name__)
CHUNK = 5000


class ReconciliationError(Exception):
    pass


def get_engine(url: str = DATABASE_URL):
    return create_engine(url, pool_pre_ping=True, future=True)


def ensure_schema(engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(SCHEMA_FILE.read_text())


# ------------------------------------------------------------------ run log
def start_run(engine, run_id: str) -> None:
    ensure_schema(engine)
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO etl_run_log (run_id, status) VALUES (:r, 'running')
                    ON CONFLICT (run_id) DO UPDATE
                    SET status = 'running', started_at = now(), finished_at = NULL,
                        error_message = NULL"""),
            {"r": run_id},
        )


def finish_run(engine, run_id: str, metrics: dict) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""UPDATE etl_run_log SET status = 'success', finished_at = now(),
                    rows_extracted = :e, rows_valid = :v, rows_rejected = :r,
                    fact_rows_added = :a WHERE run_id = :run"""),
            {"run": run_id, "e": metrics.get("rows_extracted"), "v": metrics.get("rows_valid"),
             "r": metrics.get("rows_rejected"), "a": metrics.get("fact_rows_added")},
        )


def fail_run(engine, run_id: str, error: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO etl_run_log (run_id, status, finished_at, error_message)
                    VALUES (:r, 'failed', now(), :err)
                    ON CONFLICT (run_id) DO UPDATE
                    SET status = 'failed', finished_at = now(), error_message = :err"""),
            {"r": run_id, "err": error[:2000]},
        )


# ------------------------------------------------------------------ helpers
def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of dicts with NaN/NaT replaced by None (DB NULL)."""
    obj = df.astype(object)
    return obj.where(df.notna(), None).to_dict("records")


def _chunks(rows: list, size: int = CHUNK):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def _upsert(conn, table, rows, conflict_cols, update_cols):
    if not rows:
        return
    for chunk in _chunks(rows):
        stmt = pg_insert(table)
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_cols,
                set_={c: stmt.excluded[c] for c in update_cols},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
        conn.execute(stmt, chunk)  # executemany


def _key_map(conn, table: str, nat: str, key: str) -> dict:
    return dict(conn.execute(text(f"SELECT {nat}, {key} FROM {table}")).all())


# --------------------------------------------------------------------- load
def load(engine, run_id: str, valid: pd.DataFrame, rejected: pd.DataFrame) -> dict:
    """Load one validated batch. Returns metrics about what happened."""
    if valid.empty:
        raise ValueError("No valid rows to load.")

    facts = transform.add_metrics(valid)
    dim_customer = transform.build_dim_customer(facts)
    dim_product = transform.build_dim_product(facts)
    dim_date = transform.build_dim_date(facts["order_date"].min(), facts["order_date"].max())

    meta = MetaData()
    with engine.begin() as conn:  # single atomic transaction
        meta.reflect(bind=conn, only=[
            "dim_customer", "dim_product", "dim_date", "fact_sales", "rejected_records"
        ])
        t = meta.tables

        before = conn.execute(text("SELECT count(*) FROM fact_sales")).scalar_one()

        _upsert(conn, t["dim_customer"], _records(dim_customer), ["customer_id"],
                ["customer_name", "email", "city", "country"])
        _upsert(conn, t["dim_product"], _records(dim_product), ["product_id"],
                ["product_name", "category", "list_price"])
        _upsert(conn, t["dim_date"], _records(dim_date), ["date_key"], [])

        cust_keys = _key_map(conn, "dim_customer", "customer_id", "customer_key")
        prod_keys = _key_map(conn, "dim_product", "product_id", "product_key")

        fact_df = facts.assign(
            customer_key=facts["customer_id"].map(cust_keys),
            product_key=facts["product_id"].map(prod_keys),
            order_line=facts["order_line"].astype(int),
            quantity=facts["quantity"].astype(int),
        )[["order_id", "order_line", "date_key", "customer_key", "product_key",
           "payment_method", "quantity", "unit_price", "discount",
           "gross_amount", "net_amount"]]
        fact_df["customer_key"] = fact_df["customer_key"].astype(int)
        fact_df["product_key"] = fact_df["product_key"].astype(int)

        _upsert(conn, t["fact_sales"], _records(fact_df), ["order_id", "order_line"],
                ["date_key", "customer_key", "product_key", "payment_method",
                 "quantity", "unit_price", "discount", "gross_amount", "net_amount"])

        # Reconciliation: what is in the warehouse for this batch must match the batch.
        got = conn.execute(
            text("""SELECT count(*), COALESCE(sum(f.net_amount), 0)
                    FROM fact_sales f
                    JOIN unnest(CAST(:oids AS text[]), CAST(:lines AS int[]))
                         AS b(order_id, order_line)
                      ON f.order_id = b.order_id AND f.order_line = b.order_line"""),
            {"oids": fact_df["order_id"].tolist(), "lines": fact_df["order_line"].tolist()},
        ).one()
        exp_count, exp_sum = len(fact_df), round(float(fact_df["net_amount"].sum()), 2)
        if got[0] != exp_count or abs(float(got[1]) - exp_sum) > 0.01:
            raise ReconciliationError(
                f"Warehouse has {got[0]} rows / {got[1]} net, batch has {exp_count} / {exp_sum}"
            )

        # Rejected rows are stored per run for auditing.
        if not rejected.empty:
            rej_rows = [
                {"run_id": run_id, "reject_reason": r.reject_reason,
                 "source_file": r.source_file, "payload": r.payload}
                for r in rejected.itertuples()
            ]
            conn.execute(
                text("""INSERT INTO rejected_records (run_id, reject_reason, source_file, payload)
                        VALUES (:run_id, :reject_reason, :source_file, CAST(:payload AS jsonb))"""),
                rej_rows,
            )

        after = conn.execute(text("SELECT count(*) FROM fact_sales")).scalar_one()

    metrics = {
        "fact_rows_added": int(after - before),
        "fact_rows_in_batch": exp_count,
        "customers_in_batch": len(dim_customer),
        "products_in_batch": len(dim_product),
        "net_amount_in_batch": exp_sum,
        "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    log.info("Loaded batch: %s", metrics)
    return metrics
