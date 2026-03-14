import pandas as pd


def analyze_schema(df: pd.DataFrame):

    schema = {
        "metrics": [],
        "dimensions": [],
        "time_columns": [],
        "identifiers": []
    }

    for col in df.columns:

        dtype = df[col].dtype
        col_lower = col.lower()

        # Detect time columns
        if (
            "date" in col_lower
            or "time" in col_lower
            or "timestamp" in col_lower
            or pd.api.types.is_datetime64_any_dtype(dtype)
        ):
            schema["time_columns"].append(col)
            continue

        # Detect identifiers (strict match only)
        if (
            col_lower == "id"
            or col_lower.endswith("_id")
            or col_lower.endswith("id")
            or col_lower.endswith("_code")
        ):
            schema["identifiers"].append(col)
            continue

        # Numeric → metrics
        if pd.api.types.is_numeric_dtype(dtype):
            schema["metrics"].append(col)

        else:
            schema["dimensions"].append(col)

    return schema
