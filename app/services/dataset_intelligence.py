import pandas as pd


def generate_dataset_insights(df: pd.DataFrame, schema: dict):

    insights = []

    metrics = schema.get("metrics", [])
    dimensions = schema.get("dimensions", [])
    time_cols = schema.get("time_columns", [])

    if not metrics:
        return []

    metric = metrics[0]

    # metric summary
    total = df[metric].sum()
    avg = df[metric].mean()

    insights.append(f"Total {metric} is {round(total,2)}")
    insights.append(f"Average {metric} is {round(avg,2)}")

    # best / worst dimension
    if dimensions:

        dim = dimensions[0]

        grouped = df.groupby(dim)[metric].sum()

        best = grouped.idxmax()
        worst = grouped.idxmin()

        insights.append(f"{best} has the highest {metric}")
        insights.append(f"{worst} has the lowest {metric}")

    # trend insights
    if time_cols:

        time_col = time_cols[0]

        trend = df.groupby(time_col)[metric].sum().diff()

        drop_date = trend.idxmin()
        growth_date = trend.idxmax()

        insights.append(f"Largest drop in {metric} occurred on {drop_date}")
        insights.append(f"Largest growth in {metric} occurred on {growth_date}")

    return insights[:6]
