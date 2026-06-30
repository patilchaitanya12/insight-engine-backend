import json
import logging
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# Same threshold used for dimension fuzzy matching in query_service.py —
# kept consistent so both metric and dimension matching behave the same way.
FUZZY_THRESHOLD = 75

# Bounded-scale metrics (ratings, scores, indices) shouldn't default to
# sum — summing a 0-5 score across rows just reflects row count, not
# anything meaningful. Detected by name pattern; combined with actual
# min/max range checks in _infer_aggregation below.
BOUNDED_NAME_HINTS = ["score", "rating", "index", "rank", "satisfaction", "csat", "nps"]

# Two-metric / correlation-style questions. Distinct from comparison_keywords
# ("across", "by", "compare") which assume metric vs. categorical dimension.
# These imply metric vs. metric — needs scatter, not bar.
CORRELATION_KEYWORDS = [
    "relate to", "relation between", "relationship between", "correlate",
    "correlation", "vs each other", "against", "impact on", "effect on",
    "influence on", "compared to",
]


def _metric_score(metric: str, text: str) -> int:
    """
    Scores how well a metric column name matches the question text,
    handling underscore vs space mismatches.
    """
    metric_clean = metric.lower().replace("_", " ")
    return max(
        fuzz.partial_ratio(metric_clean, text),
        fuzz.partial_ratio(metric.lower(), text),
    )


def _all_fuzzy_metrics(metrics: list[str], text: str) -> list[tuple[str, float]]:
    """Returns ALL metrics scoring at/above threshold, sorted best first —
    not just the single winner. Needed to detect tied matches (correlation
    questions naturally mention two metrics at once)."""
    if not metrics:
        return []
    scored = [(m, _metric_score(m, text)) for m in metrics]
    logger.info(f"Metric fuzzy scores: {scored}")
    hits = sorted(
        [(m, s) for m, s in scored if s >= FUZZY_THRESHOLD],
        key=lambda x: -x[1],
    )
    return hits


def _is_bounded_metric(metric_name: str, metric_stats: dict | None) -> bool:
    """
    Decides whether a metric is a bounded/non-additive scale (rating, score,
    index) vs. a genuinely additive quantity (salary, revenue, units).
    Two signals, either is sufficient:
      1. Name contains a bounded-scale hint word.
      2. Actual observed range is small (e.g. max <= 10) — typical of
         1-5 or 0-10 rating scales, vs. salaries/revenue which run into
         the thousands.
    """
    name_lower = metric_name.lower()
    if any(hint in name_lower for hint in BOUNDED_NAME_HINTS):
        return True

    if metric_stats:
        stat = metric_stats.get(metric_name)
        if stat and stat.get("max") is not None and stat["max"] <= 10:
            return True

    return False


def _infer_aggregation(metric: str, metric_stats: dict | None) -> str:
    """Defaults to avg for bounded scales, sum otherwise."""
    if _is_bounded_metric(metric, metric_stats):
        return "avg"
    return "sum"


def _detect_correlation_question(question_lower: str) -> bool:
    return any(k in question_lower for k in CORRELATION_KEYWORDS)


async def generate_query_plan(
    provider,
    question: str,
    schema_context: str,
    schema: dict,
    decomposer_hint: dict | None = None,
    metric_stats: dict | None = None,
):
    """
    decomposer_hint: the matching step from query_decomposer's output, e.g.
        {"metric": "Performance_Score", "dimension": "Leaves_Taken", "task": "..."}
    This is the decomposer's own read of the question — it should constrain
    the planner rather than being silently discarded, since today the planner
    re-derives metric/dimension from scratch and frequently disagrees with
    a perfectly correct decomposition.

    metric_stats: optional {metric_name: {"min": x, "max": y}} computed from
    the actual dataframe — lets aggregation defaults be range-aware instead
    of always defaulting to sum.
    """

    question_lower = question.lower()

    # Surface the decomposer's hint directly in the prompt so the LLM sees
    # it as a strong signal rather than re-guessing blind.
    hint_block = ""
    if decomposer_hint:
        hint_metric = decomposer_hint.get("metric")
        hint_dimension = decomposer_hint.get("dimension")
        if hint_metric or hint_dimension:
            hint_block = f"""
A prior reasoning step already analyzed this question and identified:
  - primary metric: {hint_metric}
  - primary dimension/comparison variable: {hint_dimension}
Use these unless they are clearly wrong for the available columns.
"""

    prompt = f"""
You are an expert data analytics planner.

Convert the user's question into a structured analytics plan.

Dataset schema:
{schema_context}

Available columns:
Metrics: {schema["metrics"]}
Dimensions: {schema["dimensions"]}
Time columns: {schema["time_columns"]}
{hint_block}
Rules:

1. A query plan MUST include a metric.
2. Use only columns listed above.
3. Trend queries (trend, over time, timeline, growth, change)
   → dimension must be a time column.
4. Comparison queries (across, by, compare, vs)
   → dimension must be a categorical column.
5. Distribution queries
   → aggregation = count
6. Correlation/relationship queries (relate to, correlation, impact on,
   effect on, vs each other) between TWO metrics
   → set "comparison" to the second metric, chart_type = "scatter"
7. Bounded scales (scores, ratings, indices, anything roughly 0-10)
   → aggregation = avg, NOT sum
8. Default aggregation = sum (only for genuinely additive metrics)
9. Chart rules:
   trend → line
   comparison (metric vs category) → bar
   correlation (metric vs metric) → scatter
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

        metric_hits = _all_fuzzy_metrics(schema["metrics"], question_lower)
        metric = metric_hits[0][0] if metric_hits else None

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
            "aggregation": _infer_aggregation(metric, metric_stats) if metric else "sum",
            "filters": [],
            "comparison": None,
            "trend": False,
            "chart_type": "bar",
            "group_by": None,
            "top_k": None
        }

    # ── CORRELATION DETECTION (metric vs metric) ────────────────────────────
    # Must run BEFORE metric override below, since it changes how we
    # interpret a tie between two equally-matched metrics.

    is_correlation = _detect_correlation_question(question_lower)

    # ── METRIC DETECTION FROM QUERY ───────────────────────────────────────────
    # Uses fuzzy matching so "Sleep_Hours" matches question phrasing like
    # "sleep hours" (space instead of underscore). Now returns ALL matches
    # at/above threshold, not just the top one — a correlation question
    # naturally mentions two metrics, and previously the second one was
    # silently dropped by always taking max().

    metric_hits = _all_fuzzy_metrics(schema.get("metrics", []), question_lower)

    if metric_hits:
        primary_metric = metric_hits[0][0]

        # Tie-break: if multiple metrics scored equally and this ISN'T a
        # correlation question, prefer the decomposer's metric hint over
        # whichever fuzzy match happened to sort first. Previously a tie
        # between e.g. "Age" and "Tenure_Years" (both scoring 100.0 on a
        # tenure question) was resolved arbitrarily by sort order, ignoring
        # that the decomposer had already correctly identified Tenure_Years.
        if not is_correlation and decomposer_hint:
            hint_metric = decomposer_hint.get("metric")
            tied_metrics = [m for m, s in metric_hits if s == metric_hits[0][1]]
            if hint_metric in tied_metrics:
                primary_metric = hint_metric
                logger.info(f"Metric tie broken using decomposer hint: {hint_metric}")

        plan["metric"] = primary_metric
        logger.info(f"Metric override from question: {primary_metric}")

        if is_correlation and len(metric_hits) >= 2:
            secondary_metric = next(
                (m for m, _ in metric_hits if m != primary_metric), None
            )
            if secondary_metric:
                plan["comparison"] = secondary_metric
                plan["chart_type"] = "scatter"
                logger.info(
                    f"Correlation question detected — metric={primary_metric}, "
                    f"comparison={secondary_metric}, chart_type=scatter"
                )

    # If the LLM/fuzzy match missed it but the decomposer already figured
    # out the second variable, trust that instead of leaving it blank.
    if is_correlation and not plan.get("comparison") and decomposer_hint:
        hint_dim = decomposer_hint.get("dimension")
        if hint_dim and hint_dim in schema.get("metrics", []) and hint_dim != plan.get("metric"):
            plan["comparison"] = hint_dim
            plan["chart_type"] = "scatter"
            logger.info(f"Correlation comparison filled from decomposer hint: {hint_dim}")

    # Safety net: a scatter plan's "dimension" field is irrelevant once
    # "comparison" is set (scatter is metric vs comparison, not metric vs
    # dimension). If the raw LLM output or earlier logic left dimension
    # equal to metric, code_generator would try to groupby and reset_index
    # on a column with the same name as itself, crashing pandas. Clear it.
    if is_correlation and plan.get("comparison"):
        if plan.get("dimension") == plan.get("metric"):
            plan["dimension"] = None
            logger.info("Cleared dimension — collided with metric in correlation plan")

    if not plan.get("metric") and schema["metrics"]:
        if decomposer_hint:
            hint_metric = decomposer_hint.get("metric")
            if hint_metric in schema["metrics"]:
                plan["metric"] = hint_metric
                logger.info(f"Metric set from decomposer hint (no fuzzy match): {hint_metric}")
        if not plan.get("metric"):
            plan["metric"] = schema["metrics"][0]
            logger.info(f"Auto-selected metric: {plan['metric']}")

    # ── TREND DETECTION ───────────────────────────────────────────────────────

    trend_keywords = ["trend", "over time", "timeline", "growth", "change"]

    if any(k in question_lower for k in trend_keywords) and not is_correlation:
        if schema["time_columns"]:
            plan["dimension"] = schema["time_columns"][0]
            plan["chart_type"] = "line"
            plan["trend"] = True
            logger.info("Trend query detected")

    # ── COMPARISON DETECTION (metric vs categorical dimension) ────────────────
    # Skipped when this is actually a metric-vs-metric correlation question —
    # otherwise "by" inside phrasing like "broken down by leaves taken" would
    # wrongly force dimension back to a categorical column.

    comparison_keywords = ["across", "by", "compare", "vs"]

    if any(k in question_lower for k in comparison_keywords) and not is_correlation:
        if schema["dimensions"]:
            plan["dimension"] = schema["dimensions"][0]
            plan["chart_type"] = "bar"
            logger.info("Comparison query detected")

    # ── DECOMPOSER HINT FOR DIMENSION ──────────────────────────────────────────
    # If the decomposer identified a dimension that's a real column and
    # nothing more specific has overridden it above, prefer it over the
    # planner LLM's own (often generic) first-categorical-column guess.

    if decomposer_hint and not is_correlation:
        hint_dim = decomposer_hint.get("dimension")
        all_dims = schema.get("dimensions", []) + schema.get("time_columns", [])
        if hint_dim and hint_dim in all_dims:
            plan["dimension"] = hint_dim
            logger.info(f"Dimension set from decomposer hint: {hint_dim}")

    # ── CHART HINT FROM USER ──────────────────────────────────────────────────
    # Always runs last so explicit user intent overrides any auto-detection.

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
        "scatter chart": "scatter",
        "scatter plot": "scatter",
    }
    for hint, chart in chart_hints.items():
        if hint in question_lower:
            plan["chart_type"] = chart
            logger.info(f"Chart type override from user hint: {chart}")
            break

    # ── ENSURE DIMENSION EXISTS ───────────────────────────────────────────────

    if not plan.get("dimension") and not plan.get("comparison"):
        if schema["dimensions"]:
            plan["dimension"] = schema["dimensions"][0]
        elif schema["time_columns"]:
            plan["dimension"] = schema["time_columns"][0]

    # ── GROUP BY WHEN TIME + CATEGORY ─────────────────────────────────────────

    if (
        plan.get("dimension") in schema.get("time_columns", [])
        and schema.get("dimensions")
        and plan.get("chart_type") != "grouped_bar"
    ):
        plan["group_by"] = schema["dimensions"][0]

    # ── SET group_by FOR grouped_bar ──────────────────────────────────────────

    if plan.get("chart_type") == "grouped_bar" and not plan.get("group_by"):
        if len(schema.get("dimensions", [])) > 1:
            plan["group_by"] = schema["dimensions"][1]
            logger.info(f"Auto-set group_by for grouped_bar: {plan['group_by']}")

    # ── AGGREGATION — RANGE-AWARE, NOT BLIND SUM ────────────────────────────────

    if not plan.get("aggregation"):
        plan["aggregation"] = _infer_aggregation(plan.get("metric"), metric_stats)
        logger.info(f"Auto-set aggregation: {plan['aggregation']}")
    elif plan["aggregation"] == "sum" and _is_bounded_metric(plan.get("metric", ""), metric_stats):
        # LLM defaulted to sum on a bounded scale — override even if it set
        # something explicitly, since "sum" is never meaningful here.
        plan["aggregation"] = "avg"
        logger.info(f"Overrode sum -> avg for bounded metric: {plan.get('metric')}")

    if not plan.get("filters"):
        plan["filters"] = []

    if not plan.get("chart_type"):
        plan["chart_type"] = "bar"

    # ── PREVENT TOP_K UNLESS ASKED ────────────────────────────────────────────

    if "top" not in question_lower and "highest" not in question_lower:
        plan["top_k"] = None

    logger.info(f"Final query plan: {plan}")

    return plan