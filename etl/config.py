"""Central configuration, read from environment variables with local defaults."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

RAW_DIR = Path(os.getenv("RAW_DIR", BASE_DIR / "data" / "raw"))
STAGING_DIR = Path(os.getenv("STAGING_DIR", BASE_DIR / "data" / "staging"))
SCHEMA_FILE = BASE_DIR / "sql" / "schema.sql"

# Local default points at the warehouse container exposed on host port 5433.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://warehouse:warehouse@localhost:5433/retail_dw",
)

# The run fails (nothing is loaded) if more than this share of rows is rejected.
MAX_REJECT_RATE = float(os.getenv("MAX_REJECT_RATE", "0.20"))

RAW_COLUMNS = [
    "order_id", "order_line", "order_date", "customer_id", "customer_name",
    "email", "city", "country", "product_id", "product_name", "category",
    "unit_price", "quantity", "discount", "payment_method",
]
