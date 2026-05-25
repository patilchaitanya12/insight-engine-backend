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

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ── Shared chart hint extractor ──────────────────────────────────────────────

def extract_chart_hint(question_lower: str) -> str | None:
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
    for hint, chart_type in chart_hints.items():
        if hint in question_lower:
            return chart_type
    return None


async def run_query_service(dataset_id: str, question: str):

    logger.info("===== NEW QUERY =====")
    logger.info(f"Question: {question}")
    logger.info(f"Dataset ID: {dataset_id}")

    dataset = await db.datasets.find_one({"dataset_id": dataset_id})

    if not dataset:
        logger.error("Dataset not found")
        return {"error": "Dataset not found"}

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

    schema_context = build_schema_context(df)
    provider = get_llm_provider()

    question_lower = question.lower()

    # Extract chart hint once — used across all engines
    user_chart_hint = extract_chart_hint(question_lower)

    # -------------------------------
    # Formula Engine
    # -------------------------------

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

        return {
            "table": execution_result,
            "chart": {
                "chart_type": chart_type,
                "x_column": dimension,
                "y_column": formula_metric,
                "group_by": group_by
            },
            "insights": insights
        }

    # -------------------------------
    # Difference Engine
    # -------------------------------

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

            return {
                "table": execution_result,
                "chart": {
                    "chart_type": chart_type,
                    "x_column": dimension,
                    "y_column": "Difference",
                    "group_by": group_by
                },
                "insights": insights
            }

    # -------------------------------
    # Query Memory
    # -------------------------------

    plan = None

    similar = await search_similar_query(db, dataset_id, question)

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
        steps = await decompose_query(provider, question, schema_context)
        if not isinstance(steps, list):
            steps = [{"task": question}]

    logger.info(f"Decomposed steps: {steps}")

    execution_result = {"data": []}

    for i, step in enumerate(steps[:2]):

        logger.info(f"Processing step: {step}")

        if plan is None or i > 0:
            plan = await generate_query_plan(
                provider,
                step.get("task", question),
                schema_context,
                schema
            )

        if not isinstance(plan, dict):
            continue

        plan = choose_best_dimension(df, plan, schema)

        metric = plan.get("metric")
        dimension = plan.get("dimension")

        if not metric:
            best_metric = select_best_metric(question, schema.get("metrics", []))
            if best_metric:
                plan["metric"] = best_metric
                metric = best_metric

        if "across" in question_lower or "by" in question_lower:
            for dim in schema.get("dimensions", []):
                if dim.lower() in question_lower:
                    plan["dimension"] = dim
                    plan["group_by"] = None
                    plan["trend"] = False
                    break

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
                "details": str(e)
            }

        df = pd.DataFrame(execution_result["data"])

    result_df = df

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

    if plan and plan.get("metric"):
        await db.query_history.insert_one({
            "dataset_id": dataset_id,
            "question": question,
            "plan": plan,
            "result_preview": execution_result["data"][:5],
            "timestamp": datetime.utcnow()
        })

    return {
        "table": execution_result,
        "chart": {
            "chart_type": chart_type,
            "x_column": x_column,
            "y_column": y_column,
            "group_by": plan.get("group_by") if plan else None
        },
        "insights": insights
    }