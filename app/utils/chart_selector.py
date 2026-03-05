import pandas as pd


def select_chart(chart_type: str, x_column: str, y_column: str, df: pd.DataFrame, question: str):

    x_dtype = df[x_column].dtype
    y_dtype = df[y_column].dtype
    rows = len(df)

    is_x_categorical = (
        pd.api.types.is_object_dtype(x_dtype)
        or pd.api.types.is_string_dtype(x_dtype)
        or pd.api.types.is_categorical_dtype(x_dtype)
    )

    is_y_numeric = pd.api.types.is_numeric_dtype(y_dtype)

    question_lower = question.lower()

    pie_keywords = [
        "distribution",
        "share",
        "percentage",
        "breakdown",
        "composition",
        "ratio"
    ]

    # CATEGORY vs NUMERIC
    if is_x_categorical and is_y_numeric:

        # Only use pie if the question implies distribution
        if rows <= 6 and any(k in question_lower for k in pie_keywords):
            return "pie"

        return "bar"

    # NUMERIC vs NUMERIC
    if pd.api.types.is_numeric_dtype(x_dtype) and is_y_numeric:
        return "scatter"

    return "bar"