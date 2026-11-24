import pandas as pd

from etl import transform


def test_clean_standardises_text(raw_factory):
    df = transform.clean(raw_factory([{}]))
    row = df.iloc[0]
    assert row["city"] == "Surat"
    assert row["customer_name"] == "Alice Smith"
    assert row["email"] == "alice@example.com"
    assert row["category"] == "Home"
    assert row["payment_method"] == "upi"


def test_clean_nulls_bad_email_but_keeps_row(raw_factory):
    df = transform.clean(raw_factory([{"email": "not-an-email"}]))
    assert len(df) == 1
    assert pd.isna(df.iloc[0]["email"])


def test_clean_unparseable_date_becomes_nat(raw_factory):
    df = transform.clean(raw_factory([{"order_date": "31/02/2026"}]))
    assert pd.isna(df.iloc[0]["order_date"])


def test_clean_missing_country_becomes_unknown(raw_factory):
    df = transform.clean(raw_factory([{"country": None}]))
    assert df.iloc[0]["country"] == "Unknown"


def test_keys_are_uppercased(raw_factory):
    df = transform.clean(raw_factory([{"customer_id": "c1", "order_id": "o9"}]))
    assert df.iloc[0]["customer_id"] == "C1" and df.iloc[0]["order_id"] == "O9"


def test_metrics_net_amount(raw_factory):
    df = transform.add_metrics(transform.clean(raw_factory([{}])))
    assert df.iloc[0]["gross_amount"] == 200.00
    assert df.iloc[0]["net_amount"] == 180.00
    assert df.iloc[0]["date_key"] == 20260301


def test_dim_customer_keeps_latest_attributes(raw_factory):
    raw = raw_factory([
        {"order_id": "O1", "order_date": "2026-01-01", "city": "Delhi"},
        {"order_id": "O2", "order_date": "2026-02-01", "city": "Mumbai"},
    ])
    dim = transform.build_dim_customer(transform.clean(raw))
    assert len(dim) == 1 and dim.iloc[0]["city"] == "Mumbai"


def test_dim_date_covers_range_and_flags_weekend():
    dim = transform.build_dim_date(pd.Timestamp("2026-03-02"), pd.Timestamp("2026-03-08"))
    assert len(dim) == 7
    assert dim["is_weekend"].tolist() == [False] * 5 + [True, True]  # Mon..Sun
