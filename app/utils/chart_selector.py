import pandas as pd

def select_chart(
    chart_type: str,
    x_column: str,
    y_column: str,
    df: pd.DataFrame,
    question: str,
    plan: dict | None = None
):
    # ── User/planner hint wins first ──────────────────────────────────────────
    explicit_types = {
        "line", "bar", "pie", "grouped_bar",
        "area", "scatter", "stacked_bar", "multi_line"
    }
    if chart_type in explicit_types:
        return chart_type

    # ── Fallback: auto-detect from data shape ─────────────────────────────────
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
    is_x_numeric = pd.api.types.is_numeric_dtype(x_dtype)

    question_lower = question.lower()

    # ── Plan-based detection ──────────────────────────────────────────────────
    if plan:
        if plan.get("group_by"):
            # stacked for composition, grouped for comparison
            stacked_keywords = ["stacked", "stack", "composition", "breakdown", "proportion"]
            if any(k in question_lower for k in stacked_keywords):
                return "stacked_bar"
            return "grouped_bar"

        if plan.get("trend") and is_x_datetime:
            # multi_line if multiple metrics mentioned
            multi_keywords = ["vs", "versus", "compare", "both", "and"]
            if any(k in question_lower for k in multi_keywords):
                return "multi_line"
            return "line"

        if plan.get("comparison"):
            return "grouped_bar"

        if plan.get("top_k"):
            return "bar"

    # ── Keyword-based detection ───────────────────────────────────────────────
    scatter_keywords = ["correlation", "relationship", "relate", "vs", "versus", "scatter"]
    pie_keywords = ["share", "percentage", "breakdown", "composition", "ratio", "contribution"]
    stacked_keywords = ["stacked", "stack", "proportion", "makeup"]
    area_keywords = ["area", "filled", "volume over time"]

    if any(k in question_lower for k in scatter_keywords) and is_x_numeric and is_y_numeric:
        return "scatter"

    if any(k in question_lower for k in stacked_keywords):
        return "stacked_bar"

    if any(k in question_lower for k in area_keywords) and is_x_datetime:
        return "area"

    # ── Data shape detection ──────────────────────────────────────────────────
    if is_x_datetime and is_y_numeric:
        return "line"

    if is_x_categorical and is_y_numeric:
        if rows <= 6 and any(k in question_lower for k in pie_keywords):
            return "pie"
        return "bar"

    if is_x_numeric and is_y_numeric:
        return "scatter"

    return "bar"