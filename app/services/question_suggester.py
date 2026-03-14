import json
import logging

logger = logging.getLogger(__name__)


async def generate_question_suggestions(provider, schema_context: str):

    prompt = f"""
You are a data analyst.

Based on the dataset schema below, generate 5 useful analytical questions.

Schema:
{schema_context}

Return ONLY a JSON array.

Example:
[
 "Actual_Qty trend over time",
 "Actual_Qty by Plant",
 "Top Plant by Actual_Qty",
 "Compare Planned_Qty vs Actual_Qty",
 "Scrap_Qty by Workcenter"
]
"""

    response = await provider.generate_text(prompt)

    try:
        suggestions = json.loads(response)

        if isinstance(suggestions, list):
            return suggestions[:6]

    except Exception:
        logger.warning("Invalid AI suggestions output")

    return [
        "Show trend over time",
        "Top categories by value",
        "Distribution of categories",
        "Compare key metrics",
        "Show summary statistics"
    ]
