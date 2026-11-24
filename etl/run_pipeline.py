"""Run the whole pipeline from the command line (no Airflow needed).

    python -m etl.run_pipeline                 # run id = timestamp
    python -m etl.run_pipeline --run-id demo   # re-using an id re-runs it safely
"""
import argparse
import logging
import time
from datetime import datetime

from etl import pipeline


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", default=datetime.now().strftime("manual_%Y%m%dT%H%M%S"))
    p.add_argument("--keep-staging", action="store_true")
    a = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("pipeline")
    steps = [
        ("extract", pipeline.task_extract),
        ("transform", pipeline.task_transform),
        ("validate", pipeline.task_validate),
        ("load", pipeline.task_load),
    ]
    t0 = time.time()
    try:
        for name, fn in steps:
            s = time.time()
            fn(a.run_id)
            log.info("[%s] done in %.1fs", name, time.time() - s)
    except Exception as exc:
        log.exception("Run %s failed", a.run_id)
        pipeline.task_mark_failed(a.run_id, f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)
    if not a.keep_staging:
        pipeline.cleanup(a.run_id)
    log.info("Run %s succeeded in %.1fs", a.run_id, time.time() - t0)


if __name__ == "__main__":
    main()
