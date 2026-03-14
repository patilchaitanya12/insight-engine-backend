import pandas as pd


def compute_change_metric(df, metric, group_col, date_col):
    """
    Compute change and percentage change over time for a metric.
    """

    df = df.sort_values(date_col)

    grouped = (
        df.groupby([group_col, date_col])[metric]
        .sum()
        .reset_index()
    )

    grouped["previous_value"] = (
        grouped.groupby(group_col)[metric].shift(1)
    )

    grouped["change"] = (
        grouped[metric] - grouped["previous_value"]
    )

    grouped["pct_change"] = (
        grouped["change"] / grouped["previous_value"]
    ) * 100

    return grouped

def find_biggest_drop(df, change_column="change"):
    """
    Find row with largest negative change.
    """

    worst = df.sort_values(change_column).iloc[0]

    return worst


def find_biggest_growth(df, change_column="change"):
    """
    Find row with largest positive growth.
    """

    best = df.sort_values(change_column, ascending=False).iloc[0]

    return best
