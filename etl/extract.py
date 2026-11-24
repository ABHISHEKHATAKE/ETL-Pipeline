"""Extract: read every raw CSV in the landing folder as untyped strings."""
import logging
from pathlib import Path

import pandas as pd

from etl.config import RAW_COLUMNS, RAW_DIR

log = logging.getLogger(__name__)


def extract(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    files = sorted(Path(raw_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(
            f"No CSV files in {raw_dir}. Run `python -m etl.generate_data` first."
        )

    frames = []
    for f in files:
        df = pd.read_csv(f, dtype=str)  # keep everything as text; typing is transform's job
        missing = set(RAW_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"{f.name} is missing columns: {sorted(missing)}")
        df = df[RAW_COLUMNS].copy()
        df["source_file"] = f.name
        frames.append(df)
        log.info("Read %s rows from %s", f"{len(df):,}", f.name)

    out = pd.concat(frames, ignore_index=True)
    log.info("Extracted %s rows from %d file(s)", f"{len(out):,}", len(files))
    return out
