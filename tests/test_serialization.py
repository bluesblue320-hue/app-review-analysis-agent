from __future__ import annotations

import json

import numpy as np
import pandas as pd

from backend.core.serialization import dataframe_to_records, to_json_value


def test_to_json_value_recursively_removes_non_finite_numpy_values() -> None:
    value = {
        "items": [np.int64(3), np.float64("nan"), float("inf")],
        "array": np.array([1.0, np.nan]),
    }

    result = to_json_value(value)

    assert result == {"items": [3, None, None], "array": [1.0, None]}
    assert "NaN" not in json.dumps(result, allow_nan=False)


def test_dataframe_records_convert_pandas_missing_values_to_none() -> None:
    dataframe = pd.DataFrame(
        [{"count": np.int64(2), "score": np.nan, "content": pd.NA}]
    )

    assert dataframe_to_records(dataframe) == [
        {"count": 2, "score": None, "content": None}
    ]
