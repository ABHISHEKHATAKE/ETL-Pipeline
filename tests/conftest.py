import os

import pandas as pd
import pytest
from sqlalchemy import text

from etl import load as load_mod
from etl.config import RAW_COLUMNS

TEST_DB = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://warehouse:warehouse@localhost:5433/retail_dw_test",
)


def make_raw(rows: list[dict]) -> pd.DataFrame:
    """Build a raw-style frame (all strings, like extract() returns)."""
    base = {
        "order_id": "O1", "order_line": "1", "order_date": "2026-03-01",
        "customer_id": "C1", "customer_name": "alice smith", "email": "Alice@Example.com",
        "city": "  SURAT ", "country": "India", "product_id": "P1",
        "product_name": "Widget", "category": "home", "unit_price": "100.00",
        "quantity": "2", "discount": "0.1", "payment_method": "UPI",
    }
    df = pd.DataFrame([{**base, **r} for r in rows])[RAW_COLUMNS].astype(object)
    df["source_file"] = "test.csv"
    return df


@pytest.fixture
def raw_factory():
    return make_raw


@pytest.fixture
def engine():
    """Fresh schema in a throw-away database; skipped if Postgres is unreachable."""
    eng = load_mod.get_engine(TEST_DB)
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Test Postgres not reachable (set TEST_DATABASE_URL or run `make up`)")
    with eng.begin() as c:
        c.execute(text(
            "DROP TABLE IF EXISTS fact_sales, dim_customer, dim_product, dim_date, "
            "rejected_records, etl_run_log CASCADE"
        ))
    load_mod.ensure_schema(eng)
    yield eng
    eng.dispose()
