import textwrap

AGG_MAP = {
    "avg": "mean",
    "average": "mean",
    "mean": "mean",
    "sum": "sum",
    "total": "sum",
    "count": "count",
    "max": "max",
    "min": "min"
}


def generate_pandas_code(plan: dict) -> str:
    metric = plan.get("metric")
    dimension = plan.get("dimension") or plan.get("dimensions")
    group_by = plan.get("group_by")
    comparison = plan.get("comparison")
    aggregation = AGG_MAP.get(plan.get("aggregation", "sum"), "sum")
    top_k = plan.get("top_k")
    filters = plan.get("filters") or []
    metric_formula = plan.get("metric_formula")

    code_lines = []

    # filters
    for f in filters:

        column = f.get("column")
        value = f.get("value")

        if not column:
            continue

        if isinstance(value, list):
            code_lines.append(
                f"df = df[df['{column}'].isin({value})]"
            )
        else:
            code_lines.append(
                f"df = df[df['{column}'] == '{value}']"
            )

    # computed metric
    if metric_formula:

        code_lines.append(
            f"df['computed_metric'] = {metric_formula}"
        )

        metric = "computed_metric"

    # distribution queries
    if metric == "__count__":

        if not dimension:
            raise ValueError("Distribution requires a dimension")

        code_lines.append(
            f"result = df.groupby('{dimension}').size().reset_index(name='count')"
        )

        code_lines.append(
            f"result = result.sort_values('count', ascending=False)"
        )

        if top_k:
            code_lines.append(
                f"result = result.head({top_k})"
            )

        return textwrap.dedent("\n".join(code_lines)).strip()

    # validation
    if not metric:
        raise ValueError("No metric specified in the plan")

    # ── CORRELATION / SCATTER: metric vs comparison, row-level, no groupby ──
    # When "comparison" is set, this is a metric-vs-metric question (e.g.
    # "how does performance relate to leaves taken"). Scatter plots need
    # raw row-level pairs, not an aggregated group — grouping by one of the
    # two metrics and aggregating the other would also crash if dimension
    # ever collided with metric (same column name twice in reset_index).
    if comparison:
        code_lines.append(
            f"result = df[['{metric}', '{comparison}']].dropna()"
        )
        if top_k:
            code_lines.append(
                f"result = result.sort_values('{metric}', ascending=False).head({top_k})"
            )
        return textwrap.dedent("\n".join(code_lines)).strip()

    if not dimension:
        raise ValueError("No dimension specified in the plan")

    # group by dimension + group_by
    if dimension and group_by:

        code_lines.append(
            f"result = df.groupby(['{dimension}', '{group_by}'])['{metric}'].{aggregation}().reset_index()"
        )

        code_lines.append(
            f"result = result.sort_values('{metric}', ascending=False)"
        )

        if top_k:
            code_lines.append(
                f"result = result.groupby('{group_by}').head({top_k})"
            )

    elif dimension:

        code_lines.append(
            f"result = df.groupby('{dimension}')['{metric}'].{aggregation}().reset_index()"
        )

        code_lines.append(
            f"result = result.sort_values('{metric}', ascending=False)"
        )

        if top_k:
            code_lines.append(
                f"result = result.head({top_k})"
            )

    else:

        code_lines.append(
            f"result = df[['{metric}']]"
        )

    return textwrap.dedent("\n".join(code_lines)).strip()