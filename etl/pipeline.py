"""Pipeline steps. Each step reads/writes parquet files in a per-run staging folder,
so the same functions run from the CLI and as separate Airflow tasks."""
import json
import logging
import shutil
from pathlib import Path

import pandas as pd

from etl import extract as extract_mod
from etl import load as load_mod
from etl import transform, validate as validate_mod
from etl.config import STAGING_DIR

log = logging.getLogger(__name__)


def _dir(run_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in run_id)
    d = STAGING_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _update_metrics(run_id: str, **kv) -> dict:
    path = _dir(run_id) / "metrics.json"
    m = json.loads(path.read_text()) if path.exists() else {}
    m.update(kv)
    path.write_text(json.dumps(m, indent=2))
    return m


def task_extract(run_id: str) -> int:
    load_mod.start_run(load_mod.get_engine(), run_id)
    raw = extract_mod.extract()
    raw.to_parquet(_dir(run_id) / "raw.parquet")
    _update_metrics(run_id, rows_extracted=len(raw))
    return len(raw)


def task_transform(run_id: str) -> int:
    raw = pd.read_parquet(_dir(run_id) / "raw.parquet")
    clean = transform.clean(raw)
    clean.to_parquet(_dir(run_id) / "clean.parquet")
    return len(clean)


def task_validate(run_id: str) -> float:
    d = _dir(run_id)
    raw = pd.read_parquet(d / "raw.parquet")
    clean = pd.read_parquet(d / "clean.parquet")
    valid, rejected = validate_mod.validate(clean, raw)
    valid.to_parquet(d / "valid.parquet")
    rejected.to_parquet(d / "rejected.parquet")
    _update_metrics(run_id, rows_valid=len(valid), rows_rejected=len(rejected),
                    reject_reasons=rejected["reject_reason"].value_counts().to_dict())
    return validate_mod.quality_gate(len(clean), len(rejected))


def task_load(run_id: str) -> dict:
    d = _dir(run_id)
    valid = pd.read_parquet(d / "valid.parquet")
    rejected = pd.read_parquet(d / "rejected.parquet")
    engine = load_mod.get_engine()
    result = load_mod.load(engine, run_id, valid, rejected)
    m = _update_metrics(run_id, **result)
    load_mod.finish_run(engine, run_id, m)
    return m


def task_mark_failed(run_id: str, error: str) -> None:
    load_mod.fail_run(load_mod.get_engine(), run_id, error)


def cleanup(run_id: str) -> None:
    shutil.rmtree(_dir(run_id), ignore_errors=True)
