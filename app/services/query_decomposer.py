import logging

logger = logging.getLogger(__name__)


async def decompose_query(provider, question: str, schema_context: str):

    prompt = f"""
You are an analytics reasoning engine.

Your job is to break a user question into analytical steps.

DATASET SCHEMA
{schema_context}

IMPORTANT RULES:

1. Return ONLY valid JSON.
2. Output MUST be a JSON ARRAY.
3. Each step must contain a "task".
4. Do not include explanations.
5. If the question is simple, return one step.

Correct output format example:

[
  {{
    "step": 1,
    "task": "aggregate production by plant",
    "metric": "Actual_Qty",
    "dimension": "Plant"
  }}
]

User Question:
{question}
"""

    steps = await provider.generate_structured(prompt)

    logger.info(f"Raw decomposition output: {steps}")

    # Safety: ensure list
    if isinstance(steps, dict):
        logger.warning("Decomposer returned dict instead of list, wrapping")
        steps = [steps]

    if not isinstance(steps, list):
        logger.warning("Invalid decomposition output, fallback to single step")
        return [{"task": question}]

    # Ensure each step has task
    cleaned_steps = []

    for step in steps:

        if not isinstance(step, dict):
            continue

        if "task" not in step:
            step["task"] = question

        cleaned_steps.append(step)

    if not cleaned_steps:
        cleaned_steps = [{"task": question}]

    logger.info(f"Final decomposition steps: {cleaned_steps}")

    return cleaned_steps
