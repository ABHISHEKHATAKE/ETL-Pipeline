import pytest

from etl import transform
from etl.validate import DataQualityError, quality_gate, validate


def run(raw_factory, rows):
    raw = raw_factory(rows)
    return validate(transform.clean(raw), raw)


@pytest.mark.parametrize("override,reason", [
    ({"customer_id": None}, "missing_customer_id"),
    ({"product_id": None}, "missing_product_id"),
    ({"order_date": "31/02/2026"}, "invalid_order_date"),
    ({"order_date": "2099-01-01"}, "future_order_date"),
    ({"quantity": "-1"}, "invalid_quantity"),
    ({"quantity": "0"}, "invalid_quantity"),
    ({"quantity": "abc"}, "invalid_quantity"),
    ({"unit_price": "-5"}, "invalid_unit_price"),
    ({"discount": "1.5"}, "invalid_discount"),
])
def test_each_rule_rejects_with_reason(raw_factory, override, reason):
    valid, rejected = run(raw_factory, [override])
    assert valid.empty
    assert rejected["reject_reason"].tolist() == [reason]


def test_good_row_passes(raw_factory):
    valid, rejected = run(raw_factory, [{}])
    assert len(valid) == 1 and rejected.empty


def test_duplicate_keeps_first_and_rejects_rest(raw_factory):
    valid, rejected = run(raw_factory, [{}, {}, {"order_line": "2"}])
    assert len(valid) == 2
    assert rejected["reject_reason"].tolist() == ["duplicate_order_line"]


def test_bad_first_copy_does_not_hide_good_second_copy(raw_factory):
    valid, rejected = run(raw_factory, [{"quantity": "-1"}, {"quantity": "2"}])
    assert len(valid) == 1
    assert rejected["reject_reason"].tolist() == ["invalid_quantity"]


def test_rejected_payload_keeps_original_raw_value(raw_factory):
    _, rejected = run(raw_factory, [{"order_date": "31/02/2026"}])
    assert "31/02/2026" in rejected.iloc[0]["payload"]


def test_quality_gate():
    assert quality_gate(100, 5, max_rate=0.2) == 0.05
    with pytest.raises(DataQualityError):
        quality_gate(100, 30, max_rate=0.2)
