import pandas as pd


def select_chart(
    chart_type: str,
    x_column: str,
    y_column: str,
    df: pd.DataFrame,
    question: str,
    plan: dict | None = None
):

    if x_column not in df.columns or y_column not in df.columns:
        return "bar"

    try:
        x_dtype = df[x_column].dtype
        y_dtype = df[y_column].dtype
    except Exception:
        return "bar"

    rows = len(df)

    is_x_categorical = (
        pd.api.types.is_object_dtype(x_dtype)
        or pd.api.types.is_string_dtype(x_dtype)
        or pd.api.types.is_categorical_dtype(x_dtype)
    )

    is_y_numeric = pd.api.types.is_numeric_dtype(y_dtype)
    is_x_datetime = pd.api.types.is_datetime64_any_dtype(x_dtype)

    question_lower = question.lower()

    if plan:

        if plan.get("group_by"):
            return "grouped_bar"

        if plan.get("trend") and is_x_datetime:
            return "line"

        if plan.get("comparison"):
            return "grouped_bar"

        if plan.get("top_k"):
            return "bar"

        if plan.get("metric") == "__count__":
            return "bar"

    pie_keywords = [
        "distribution",
        "share",
        "percentage",
        "breakdown",
        "composition",
        "ratio",
        "contribution"
    ]

    if is_x_datetime and is_y_numeric:
        return "line"

    if is_x_categorical and is_y_numeric:

        if rows <= 6 and any(k in question_lower for k in pie_keywords):
            return "pie"

        return "bar"

    if pd.api.types.is_numeric_dtype(x_dtype) and is_y_numeric:
        return "scatter"

    return "bar"
