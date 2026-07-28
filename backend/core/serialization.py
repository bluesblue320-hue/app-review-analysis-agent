"""Convert pandas and NumPy values into JSON-compatible Python values."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def to_json_value(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    return value


def dataframe_to_records(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    if dataframe is None or dataframe.empty:
        return []
    return [
        {str(key): to_json_value(value) for key, value in record.items()}
        for record in dataframe.to_dict(orient="records")
    ]
