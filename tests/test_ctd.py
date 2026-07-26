from __future__ import annotations

import pandas as pd

from preprocessing.ctd import load_ctd_raw


def test_load_ctd_raw_coerces_measurement_columns(tmp_path):
    source = tmp_path / "ctd.tsv"
    source.write_text(
        "label\tdate\tdepth\ttemperature\n"
        "2024-01-O-s1\t2024-01-02\t0.5\t12.3\n"
        "2024-01-O-s1\t2024-01-02\t1.0\tinvalid\n",
        encoding="utf-8",
    )

    frame = load_ctd_raw(source)

    assert frame["depth_m"].tolist() == [0.5, 1.0]
    assert frame.loc[0, "temperature"] == 12.3
    assert pd.isna(frame.loc[1, "temperature"])
