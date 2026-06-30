import pandas as pd
import logging
from datetime import datetime

from app.core.database import db
from app.services.llm.factory import get_llm_provider
from app.services.query_planner import generate_query_plan
from app.services.query_decomposer import decompose_query
from app.services.code_generator import generate_pandas_code
from app.services.insight_generator import generate_insights
from app.services.schema_analyzer import analyze_schema
from app.services.query_memory import search_similar_query

from app.services.metric_engine import (
    compute_change_metric,
    find_biggest_drop,
    find_biggest_growth
)

from app.utils.code_executor import CodeExecutor
from app.utils.column_utils import correct_column_name
from app.utils.chart_selector import select_chart
from app.utils.schema_builder import build_schema_context
from app.utils.metric_selector import select_best_metric
from app.utils.dimension_ranker import choose_best_dimension
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def extract_chart_hint(question_lower: str) -> str | None:
    chart_hints = {
        "grouped bar": "grouped_bar",
        "grouped_bar": "grouped_bar",
        "stacked bar": "stacked_bar",
        "stacked_bar": "stacked_bar",
        "bar chart": "bar",
        "bar graph": "bar",
        "line chart": "line",
        "line graph": "line",
        "multi line": "multi_line",
        "multiple lines": "multi_line",
        "area chart": "area",
        "area graph": "area",
        "scatter chart": "scatter",
        "scatter plot": "scatter",
        "correlation": "scatter",
        "pie chart": "pie",
        "pie graph": "pie",
        "trend chart": "line",
    }
    for hint, chart_type in chart_hints.items():
        if hint in question_lower:
            return chart_type
    return None


async def _save_history(
    user_id: str,
    dataset_id: str,
    question: str,
    plan: dict | None,
    execution_result: dict,
    chart: dict,
    insights: str,
) -> str | None:
    """
    Always saves a query_history document — even for formula/difference
    engine results — so every query result can receive feedback.

    Returns the inserted document's _id as a string (query_id),
    or None if the insert failed.
    """
    try:
        doc = await db.query_history.insert_one({
            "user_id": user_id,
            "dataset_id": dataset_id,
            "question": question,
            "plan": plan,
            "chart": chart,
            "insights": insights,
            "result_preview": execution_result.get("data", [])[:5],
            "timestamp": datetime.utcnow()
        })
        inserted_id = str(doc.inserted_id)
        logger.info(f"Saved query_history: _id={inserted_id} user={user_id} dataset={dataset_id}")
        return inserted_id
    except Exception as e:
        logger.error(f"Failed to save query_history: {e}")
        return None


async def run_query_service(dataset_id: str, question: str, user_id: str):

    logger.info("===== NEW QUERY =====")
    logger.info(f"Question: {question}")
    logger.info(f"Dataset ID: {dataset_id}")

    dataset = await db.datasets.find_one({
        "dataset_id": dataset_id,
        "user_id": user_id,
    })

    if not dataset:
        logger.error(f"Dataset not found or not owned by user {user_id}")
        return {"error": "Dataset not found", "query_id": None}

    df = pd.DataFrame(dataset["data"])
    logger.info(f"Dataset loaded with shape: {df.shape}")

    for col in df.columns:
        if "date" in col.lower():
            df[col] = pd.to_datetime(df[col], errors="coerce")

    df = df.drop(
        columns=[c for c in df.columns if "sr" in c.lower()],
        errors="ignore"
    )

    logger.info(f"Columns after cleanup: {df.columns.tolist()}")

    schema = analyze_schema(df)
    logger.info(f"Schema detected: {schema}")

    # Min/max per numeric metric — lets the planner tell a bounded scale
    # (e.g. Performance_Score 0-5) apart from a genuinely additive metric
    # (e.g. Monthly_Salary), instead of always defaulting aggregation to sum.
    metric_stats = {}
    for col in schema.get("metrics", []):
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if not series.empty:
                metric_stats[col] = {
                    "min": float(series.min()),
                    "max": float(series.max()),
                }
    logger.info(f"Metric stats: {metric_stats}")

    schema_context = build_schema_context(df)
    provider = get_llm_provider()

    question_lower = question.lower()

    # Extract chart hint once — used across all engines
    user_chart_hint = extract_chart_hint(question_lower)

    # Formula Engine

    formula_metric = None

    if "efficiency" in question_lower and "Actual_Qty" in df.columns and "Planned_Qty" in df.columns:
        df["Efficiency"] = df["Actual_Qty"] / df["Planned_Qty"]
        formula_metric = "Efficiency"

    if "scrap rate" in question_lower and "Scrap_Qty" in df.columns and "Actual_Qty" in df.columns:
        df["Scrap_Rate"] = df["Scrap_Qty"] / df["Actual_Qty"]
        formula_metric = "Scrap_Rate"

    if "rework rate" in question_lower and "Rework_Qty" in df.columns and "Actual_Qty" in df.columns:
        df["Rework_Rate"] = df["Rework_Qty"] / df["Actual_Qty"]
        formula_metric = "Rework_Rate"

    if "cost variance" in question_lower and "Actual_Cost" in df.columns and "Planned_Cost" in df.columns:
        df["Cost_Variance"] = df["Actual_Cost"] - df["Planned_Cost"]
        formula_metric = "Cost_Variance"

    if formula_metric:

        dimension = schema["dimensions"][0] if schema["dimensions"] else df.columns[0]

        result = (
            df.groupby(dimension)[formula_metric]
            .mean()
            .reset_index()
        )

        execution_result = {
            "columns": result.columns.tolist(),
            "data": result.to_dict("records")
        }

        chart_type = user_chart_hint or "bar"

        group_by = None
        if chart_type == "grouped_bar" and len(schema.get("dimensions", [])) > 1:
            group_by = schema["dimensions"][1]

        insights = await generate_insights(provider, result, question)

        chart = {
            "chart_type": chart_type,
            "x_column": dimension,
            "y_column": formula_metric,
            "group_by": group_by,
            "aggregation": "avg",  # formula metrics (efficiency, scrap rate, etc.) are ratios — never sum
        }

        query_id = await _save_history(
            user_id, dataset_id, question,
            plan={"metric": formula_metric, "dimension": dimension, "engine": "formula"},
            execution_result=execution_result,
            chart=chart,
            insights=insights,
        )

        return {
            "query_id": query_id,
            "table": execution_result,
            "chart": chart,
            "insights": insights
        }

    # Difference Engine

    difference_keywords = ["difference", "gap", "variance", "compare"]

    if any(k in question_lower for k in difference_keywords):

        metric_cols = schema.get("metrics", [])

        metric_a = None
        metric_b = None

        for m in metric_cols:
            if m.lower() in question_lower:
                if metric_a is None:
                    metric_a = m
                else:
                    metric_b = m
                    break

        if not metric_a or not metric_b:
            planned_cols = [c for c in metric_cols if "plan" in c.lower()]
            actual_cols = [c for c in metric_cols if "actual" in c.lower()]

            if planned_cols and actual_cols:
                metric_a = planned_cols[0]
                metric_b = actual_cols[0]

        if metric_a and metric_b:

            df["Difference"] = df[metric_a].astype(float) - df[metric_b].astype(float)

            dimension = schema["dimensions"][0] if schema["dimensions"] else df.columns[0]

            result = (
                df.groupby(dimension)["Difference"]
                .sum()
                .reset_index()
                .sort_values("Difference", ascending=False)
            )

            execution_result = {
                "columns": result.columns.tolist(),
                "data": result.to_dict("records")
            }

            chart_type = user_chart_hint or "bar"

            group_by = None
            if chart_type == "grouped_bar" and len(schema.get("dimensions", [])) > 1:
                group_by = schema["dimensions"][1]

            insights = await generate_insights(provider, result, question)

            chart = {
                "chart_type": chart_type,
                "x_column": dimension,
                "y_column": "Difference",
                "group_by": group_by,
                "aggregation": "sum",
            }

            query_id = await _save_history(
                user_id, dataset_id, question,
                plan={"metric_a": metric_a, "metric_b": metric_b, "dimension": dimension, "engine": "difference"},
                execution_result=execution_result,
                chart=chart,
                insights=insights,
            )

            return {
                "query_id": query_id,
                "table": execution_result,
                "chart": chart,
                "insights": insights
            }

    # Query Memory

    plan = None

    similar = await search_similar_query(db, dataset_id, question, user_id=user_id)

    if similar and similar.get("plan"):
        cached_plan = similar["plan"]
        if cached_plan.get("metric"):
            plan = cached_plan
            steps = [{"task": question}]
        else:
            steps = None
    else:
        steps = None

    if steps is None:
        raw_steps = await decompose_query(provider, question, schema_context)
        if not isinstance(raw_steps, list):
            raw_steps = [{"task": question}]

        # Unwrap nested steps: decomposer sometimes returns [{steps:[...], task:"..."}]
        # instead of a flat list. Flatten it so each inner step becomes a top-level step.
        steps = []
        for s in raw_steps:
            if isinstance(s, dict) and "steps" in s and isinstance(s["steps"], list):
                for inner in s["steps"]:
                    if isinstance(inner, dict):
                        if "task" not in inner:
                            inner["task"] = s.get("task", question)
                        steps.append(inner)
            else:
                steps.append(s)

        if not steps:
            steps = [{"task": question}]

    logger.info(f"Decomposed steps: {steps}")

    execution_result = {"data": []}
    original_df = df.copy()  # preserve original — never mutate between steps

    for i, step in enumerate(steps[:2]):

        logger.info(f"Processing step: {step}")

        # Always plan against the original question, not the step sub-task,
        # so the planner has full schema context on every iteration.
        if plan is None or i > 0:
            plan = await generate_query_plan(
                provider,
                step.get("task", question),
                schema_context,
                schema,
                decomposer_hint=step,
                metric_stats=metric_stats,
            )

        if not isinstance(plan, dict):
            continue

        # Always execute against original_df so all columns are available.
        # The multi-step loop is for planning refinement, not chained transforms.
        df = original_df.copy()

        plan = choose_best_dimension(df, plan, schema)

        metric = plan.get("metric")
        dimension = plan.get("dimension")

        if not metric:
            best_metric = select_best_metric(question, schema.get("metrics", []))
            if best_metric:
                plan["metric"] = best_metric
                metric = best_metric

        if "across" in question_lower or "by" in question_lower or "each" in question_lower:
            # rapidfuzz partial_ratio: scores how much of dim name appears in question.
            # Threshold 75 catches plurals, underscores, partial words
            # e.g. "Category"  vs "categories"       → ~89
            #      "Member"    vs "members"           → ~91
            #      "Is_Essential" vs "essential"      → ~82
            #      "Payment_Mode" vs "payment mode"   → ~87
            FUZZY_THRESHOLD = 75

            def dim_score(dim: str, text: str) -> int:
                # Clean underscores so "Payment_Mode" → "payment mode"
                dim_clean = dim.lower().replace("_", " ")
                return max(
                    fuzz.partial_ratio(dim_clean, text),
                    fuzz.partial_ratio(dim.lower(), text),
                )

            scored_dims = [
                (dim, dim_score(dim, question_lower))
                for dim in schema.get("dimensions", [])
            ]
            logger.info(f"Dimension fuzzy scores: {scored_dims}")

            matched_dims = [
                dim for dim, score in scored_dims
                if score >= FUZZY_THRESHOLD
            ]
            logger.info(f"Matched dimensions from question: {matched_dims}")

            if len(matched_dims) >= 2:
                # e.g. "by each member across different categories"
                # → dimension=first matched, group_by=second matched, grouped_bar
                plan["dimension"] = matched_dims[0]
                plan["group_by"] = matched_dims[1]
                plan["chart_type"] = "grouped_bar"
                plan["trend"] = False
                logger.info(f"Multi-dim query: dimension={matched_dims[0]}, group_by={matched_dims[1]}")
            elif len(matched_dims) == 1:
                plan["dimension"] = matched_dims[0]
                plan["group_by"] = None
                plan["trend"] = False

        if isinstance(dimension, str) and "," in dimension:
            dimension = [d.strip() for d in dimension.split(",")]
            plan["dimension"] = dimension

        if not metric and plan.get("aggregation") == "count":
            dimension = plan.get("dimension")
            if dimension:
                plan["metric"] = dimension

        if ("trend" in question_lower or "over time" in question_lower) and schema.get("time_columns"):
            plan["dimension"] = schema["time_columns"][0]
            if not plan.get("metric") and schema.get("metrics"):
                plan["metric"] = schema["metrics"][0]

        if not plan.get("metric"):
            continue

        if plan.get("trend"):
            plan["group_by"] = None

        if "top" not in question_lower and "highest" not in question_lower:
            plan["top_k"] = None

        # Apply user chart hint to plan
        if user_chart_hint:
            plan["chart_type"] = user_chart_hint
            logger.info(f"Chart type override from user: {user_chart_hint}")

        code = generate_pandas_code(plan).strip()

        try:
            execution_result = CodeExecutor.execute(code, df)
        except Exception as e:
            logger.error(code)
            logger.exception(e)
            return {
                "error": "AI generated invalid analysis logic.",
                "details": str(e),
                "query_id": None,
            }

    result_df = pd.DataFrame(execution_result["data"]) if execution_result.get("data") else original_df

    try:
        if plan and plan.get("comparison") in ["drop", "growth"] and "Date" in dataset["data"][0]:
            metric = plan.get("metric")
            dimension = plan.get("dimension")
            change_df = compute_change_metric(result_df, metric, dimension, "Date")
            if plan.get("comparison") == "drop":
                find_biggest_drop(change_df)
            if plan.get("comparison") == "growth":
                find_biggest_growth(change_df)
    except Exception:
        pass

    dimension = plan.get("dimension") if plan else ""
    metric = plan.get("metric") if plan else ""

    x_column = correct_column_name(dimension, list(result_df.columns))
    y_column = correct_column_name(metric, list(result_df.columns))

    if plan and plan.get("trend") and "Date" in result_df.columns:
        x_column = "Date"

    if not x_column or not y_column:
        numeric_cols = result_df.select_dtypes(include=["number"]).columns.tolist()
        categorical_cols = result_df.select_dtypes(exclude=["number"]).columns.tolist()
        if categorical_cols and numeric_cols:
            x_column = categorical_cols[0]
            y_column = numeric_cols[0]
        elif len(result_df.columns) >= 2:
            x_column = result_df.columns[0]
            y_column = result_df.columns[1]

    if x_column == y_column and len(result_df.columns) >= 2:
        y_column = result_df.columns[1]

    chart_type = select_chart(
        plan.get("chart_type", "bar") if plan else "bar",
        x_column,
        y_column,
        result_df,
        question,
        plan
    )

    insights = await generate_insights(provider, result_df, question)

    chart = {
        "chart_type": chart_type,
        "x_column": x_column,
        "y_column": y_column,
        "group_by": plan.get("group_by") if plan else None,
        "aggregation": plan.get("aggregation", "sum") if plan else "sum",
    }

    query_id = await _save_history(
        user_id, dataset_id, question,
        plan=plan,
        execution_result=execution_result,
        chart=chart,
        insights=insights,
    )

    logger.info(f"===== RETURNING RESPONSE ===== query_id={query_id}")

    return {
        "query_id": query_id,
        "table": execution_result,
        "chart": chart,
        "insights": insights
    }