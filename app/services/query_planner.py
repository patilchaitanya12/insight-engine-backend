import json
import logging

logger = logging.getLogger(__name__)


async def generate_query_plan(provider, question: str, schema_context: str, schema: dict):

    question_lower = question.lower()

    prompt = f"""
You are an expert data analytics planner.

Convert the user's question into a structured analytics plan.

Dataset schema:
{schema_context}

Available columns:
Metrics: {schema["metrics"]}
Dimensions: {schema["dimensions"]}
Time columns: {schema["time_columns"]}

Rules:

1. A query plan MUST include a metric.
2. Use only columns listed above.
3. Trend queries (trend, over time, timeline, growth, change)
   → dimension must be a time column.
4. Comparison queries (across, by, compare, vs)
   → dimension must be a categorical column.
5. Distribution queries
   → aggregation = count
6. Default aggregation = sum
7. Chart rules:
   trend → line
   comparison → bar
   distribution → bar
   time + category → grouped_bar

Return ONLY JSON.

Example output:

{{
"metric": "Actual_Qty",
"dimension": "Plant",
"group_by": null,
"aggregation": "sum",
"filters": [],
"comparison": null,
"trend": false,
"chart_type": "bar",
"top_k": null
}}
"""

    plan = await provider.generate_structured(prompt)

    logger.info(f"Raw planner output: {plan}")

    # ── FALLBACK IF LLM RETURNS BAD DATA ──────────────────────────────────────

    if not isinstance(plan, dict):

        logger.warning("Planner returned invalid output")

        metric = None
        for m in schema["metrics"]:
            if m.lower() in question_lower:
                metric = m
                break

        if not metric and schema["metrics"]:
            metric = schema["metrics"][0]

        dimension = None
        if schema["dimensions"]:
            dimension = schema["dimensions"][0]
        elif schema["time_columns"]:
            dimension = schema["time_columns"][0]

        return {
            "metric": metric,
            "dimension": dimension,
            "aggregation": "sum",
            "filters": [],
            "comparison": None,
            "trend": False,
            "chart_type": "bar",
            "group_by": None,
            "top_k": None
        }

    # ── METRIC DETECTION FROM QUERY ───────────────────────────────────────────

    if schema.get("metrics"):
        for metric in schema["metrics"]:
            if metric.lower() in question_lower:
                plan["metric"] = metric
                logger.info(f"Metric override from question: {metric}")
                break

    if not plan.get("metric") and schema["metrics"]:
        plan["metric"] = schema["metrics"][0]
        logger.info(f"Auto-selected metric: {plan['metric']}")

    # ── TREND DETECTION ───────────────────────────────────────────────────────

    trend_keywords = ["trend", "over time", "timeline", "growth", "change"]

    if any(k in question_lower for k in trend_keywords):
        if schema["time_columns"]:
            plan["dimension"] = schema["time_columns"][0]
            plan["chart_type"] = "line"
            plan["trend"] = True
            logger.info("Trend query detected")

    # ── COMPARISON DETECTION ──────────────────────────────────────────────────

    comparison_keywords = ["across", "by", "compare", "vs"]

    if any(k in question_lower for k in comparison_keywords):
        if schema["dimensions"]:
            plan["dimension"] = schema["dimensions"][0]
            plan["chart_type"] = "bar"
            logger.info("Comparison query detected")

    # ── CHART HINT FROM USER ──────────────────────────────────────────────────
    # Always runs last so user intent overrides any auto-detection above

    chart_hints = {
        "grouped bar": "grouped_bar",
        "grouped_bar": "grouped_bar",
        "bar chart": "bar",
        "bar graph": "bar",
        "line chart": "line",
        "line graph": "line",
        "area chart": "line",
        "pie chart": "pie",
        "pie graph": "pie",
        "trend chart": "line",
    }
    for hint, chart in chart_hints.items():
        if hint in question_lower:
            plan["chart_type"] = chart
            logger.info(f"Chart type override from user hint: {chart}")
            break

    # ── ENSURE DIMENSION EXISTS ───────────────────────────────────────────────

    if not plan.get("dimension"):
        if schema["dimensions"]:
            plan["dimension"] = schema["dimensions"][0]
        elif schema["time_columns"]:
            plan["dimension"] = schema["time_columns"][0]

    # ── GROUP BY WHEN TIME + CATEGORY ─────────────────────────────────────────

    if (
        plan.get("dimension") in schema.get("time_columns", [])
        and schema.get("dimensions")
        and plan.get("chart_type") != "grouped_bar"  # don't override explicit grouped_bar
    ):
        plan["group_by"] = schema["dimensions"][0]

    # ── SET group_by FOR grouped_bar ──────────────────────────────────────────

    if plan.get("chart_type") == "grouped_bar" and not plan.get("group_by"):
        if len(schema.get("dimensions", [])) > 1:
            plan["group_by"] = schema["dimensions"][1]
            logger.info(f"Auto-set group_by for grouped_bar: {plan['group_by']}")

    # ── DEFAULTS ──────────────────────────────────────────────────────────────

    if not plan.get("aggregation"):
        plan["aggregation"] = "sum"

    if not plan.get("filters"):
        plan["filters"] = []

    if not plan.get("chart_type"):
        plan["chart_type"] = "bar"

    # ── PREVENT TOP_K UNLESS ASKED ────────────────────────────────────────────

    if "top" not in question_lower and "highest" not in question_lower:
        plan["top_k"] = None

    logger.info(f"Final query plan: {plan}")

    return plan