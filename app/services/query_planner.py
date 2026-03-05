async def generate_query_plan(provider, question: str, columns_info: str):

    prompt = f"""
You are an analytics query planner.

A pandas dataframe named df exists.

DATASET SCHEMA
{columns_info}

Your job is to convert the user's question into a structured analytics plan.

Understand analytical intent such as:
- ranking
- comparison
- contribution
- trend
- filtering

Rules:

1. Metric MUST be from numeric columns.
2. Dimension MUST be from categorical columns.
3. Use ONLY column names from the dataset.
4. If user asks "top", "highest", "best" → set top_k.
5. If user asks "trend" → set trend=true and chart_type="line".
6. If user asks "share", "contribution", "distribution" → chart_type="pie".
7. If comparing categories → chart_type="bar".
8. If time-based analysis → dimension should be date/time column.

Filters:

If user mentions a specific category value
Example:
"sales in India"

Return:

filters: [
  {{
   "column": "Country",
   "value": "India"
  }}
]

For multiple values:

"value": ["India","Japan"]

Default aggregation = "sum".

Return ONLY JSON.

FORMAT:

{{
 "metric": "numeric column",
 "dimension": "categorical column",
 "group_by": null,
 "aggregation": "sum | avg | count | max | min",
 "top_k": null,
 "filters": [],
 "comparison": null,
 "trend": false,
 "chart_type": "bar | line | pie | scatter"
}}

User Question:
{question}
"""

    plan = await provider.generate_structured(prompt)

    return plan
