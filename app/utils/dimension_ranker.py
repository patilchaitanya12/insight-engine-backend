import pandas as pd


def rank_dimensions(df: pd.DataFrame, dimensions: list[str]) -> list[str]:
    """
    Rank categorical dimensions by cardinality (lowest unique values first).
    Lower cardinality dimensions produce better charts.
    """

    scores = []

    for dim in dimensions:

        if dim not in df.columns:
            continue

        try:
            unique_count = df[dim].nunique()

            scores.append((dim, unique_count))

        except Exception:
            continue

    scores.sort(key=lambda x: x[1])

    return [d[0] for d in scores]


def choose_best_dimension(df: pd.DataFrame, plan: dict, schema: dict) -> dict:
    """
    Adjust planner dimension if cardinality is too high.
    """

    dimensions = schema.get("dimensions", [])

    if not dimensions:
        return plan

    ranked = rank_dimensions(df, dimensions)

    current_dim = plan.get("dimension")

    if current_dim not in df.columns:
        plan["dimension"] = ranked[0]
        return plan

    # Prevent charts with too many bars
    if df[current_dim].nunique() > 30:

        best = ranked[0]

        plan["dimension"] = best

    return plan
