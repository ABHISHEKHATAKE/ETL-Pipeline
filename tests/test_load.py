"""Integration tests against a real Postgres (skipped if none is reachable)."""
import pytest
from sqlalchemy import text

from etl import load, transform
from etl.validate import validate


def prepare(raw_factory, rows):
    raw = raw_factory(rows)
    return validate(transform.clean(raw), raw)


def count(engine, table):
    with engine.connect() as c:
        return c.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


ROWS = [
    {"order_id": "O1", "order_line": "1"},
    {"order_id": "O1", "order_line": "2", "product_id": "P2", "product_name": "Gadget"},
    {"order_id": "O2", "order_line": "1", "customer_id": "C2", "customer_name": "bob"},
    {"order_id": "O3", "order_line": "1", "quantity": "-4"},  # rejected
]


def test_load_populates_star_schema(engine, raw_factory):
    valid, rejected = prepare(raw_factory, ROWS)
    m = load.load(engine, "t1", valid, rejected)
    assert m["fact_rows_added"] == 3
    assert count(engine, "fact_sales") == 3
    assert count(engine, "dim_customer") == 2
    assert count(engine, "dim_product") == 2
    assert count(engine, "rejected_records") == 1


def test_reload_is_idempotent(engine, raw_factory):
    valid, rejected = prepare(raw_factory, ROWS)
    load.load(engine, "t1", valid, rejected)
    second = load.load(engine, "t2", valid, rejected)
    assert second["fact_rows_added"] == 0
    assert count(engine, "fact_sales") == 3
    assert count(engine, "dim_customer") == 2


def test_dimension_attributes_update_on_reload(engine, raw_factory):
    valid, rejected = prepare(raw_factory, [{"city": "Delhi"}])
    load.load(engine, "t1", valid, rejected)
    valid, rejected = prepare(raw_factory, [{"order_date": "2026-04-01", "city": "Mumbai"}])
    load.load(engine, "t2", valid, rejected)
    with engine.connect() as c:
        city = c.execute(text("SELECT city FROM dim_customer WHERE customer_id='C1'")).scalar_one()
    assert city == "Mumbai"


def test_failed_load_rolls_back_everything(engine, raw_factory):
    """The rejected-records insert is the LAST step of the transaction. Make it fail
    (NOT NULL violation) and check that the fact/dimension inserts before it vanish."""
    valid, rejected = prepare(raw_factory, ROWS)
    assert not rejected.empty
    rejected = rejected.assign(reject_reason=None)
    with pytest.raises(Exception):
        load.load(engine, "t1", valid, rejected)
    assert count(engine, "fact_sales") == 0
    assert count(engine, "dim_customer") == 0


def test_run_log_lifecycle(engine):
    load.start_run(engine, "r1")
    load.fail_run(engine, "r1", "boom")
    with engine.connect() as c:
        row = c.execute(text("SELECT status, error_message FROM etl_run_log")).one()
    assert row == ("failed", "boom")
