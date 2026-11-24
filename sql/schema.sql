-- Star schema for retail sales, plus audit tables.
-- Safe to run repeatedly (everything is IF NOT EXISTS).

-- ---------------------------------------------------------------- dimensions
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key   SERIAL PRIMARY KEY,           -- surrogate key
    customer_id    VARCHAR(20)  NOT NULL UNIQUE, -- natural / business key
    customer_name  VARCHAR(200),
    email          VARCHAR(255),
    city           VARCHAR(100),
    country        VARCHAR(100),
    updated_at     TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key    SERIAL PRIMARY KEY,
    product_id     VARCHAR(20)  NOT NULL UNIQUE,
    product_name   VARCHAR(200),
    category       VARCHAR(100),
    list_price     NUMERIC(12,2),
    updated_at     TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key       INTEGER PRIMARY KEY,          -- yyyymmdd
    full_date      DATE    NOT NULL UNIQUE,
    year           SMALLINT NOT NULL,
    quarter        SMALLINT NOT NULL,
    month          SMALLINT NOT NULL,
    month_name     VARCHAR(12) NOT NULL,
    day            SMALLINT NOT NULL,
    day_of_week    SMALLINT NOT NULL,            -- 1 = Monday
    day_name       VARCHAR(12) NOT NULL,
    is_weekend     BOOLEAN NOT NULL
);

-- --------------------------------------------------------------------- fact
CREATE TABLE IF NOT EXISTS fact_sales (
    sales_key      BIGSERIAL PRIMARY KEY,
    order_id       VARCHAR(20) NOT NULL,
    order_line     INTEGER     NOT NULL,
    date_key       INTEGER     NOT NULL REFERENCES dim_date(date_key),
    customer_key   INTEGER     NOT NULL REFERENCES dim_customer(customer_key),
    product_key    INTEGER     NOT NULL REFERENCES dim_product(product_key),
    payment_method VARCHAR(30),
    quantity       INTEGER      NOT NULL CHECK (quantity > 0),
    unit_price     NUMERIC(12,2) NOT NULL CHECK (unit_price > 0),
    discount       NUMERIC(4,3)  NOT NULL CHECK (discount >= 0 AND discount <= 1),
    gross_amount   NUMERIC(14,2) NOT NULL,
    net_amount     NUMERIC(14,2) NOT NULL,
    loaded_at      TIMESTAMP NOT NULL DEFAULT now(),
    -- This constraint is what makes reloads idempotent (upsert target).
    CONSTRAINT uq_fact_sales_order_line UNIQUE (order_id, order_line)
);
CREATE INDEX IF NOT EXISTS ix_fact_sales_date     ON fact_sales(date_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_customer ON fact_sales(customer_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_product  ON fact_sales(product_key);

-- -------------------------------------------------------------------- audit
CREATE TABLE IF NOT EXISTS rejected_records (
    reject_id      BIGSERIAL PRIMARY KEY,
    run_id         VARCHAR(100) NOT NULL,
    reject_reason  VARCHAR(60)  NOT NULL,
    source_file    VARCHAR(255),
    payload        JSONB NOT NULL,               -- the original raw row
    rejected_at    TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rejected_run ON rejected_records(run_id);

CREATE TABLE IF NOT EXISTS etl_run_log (
    run_id          VARCHAR(100) PRIMARY KEY,
    started_at      TIMESTAMP NOT NULL DEFAULT now(),
    finished_at     TIMESTAMP,
    status          VARCHAR(20) NOT NULL,        -- running | success | failed
    rows_extracted  INTEGER,
    rows_valid      INTEGER,
    rows_rejected   INTEGER,
    fact_rows_added INTEGER,
    error_message   TEXT
);
