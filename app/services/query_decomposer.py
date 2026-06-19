import logging

logger = logging.getLogger(__name__)


async def decompose_query(provider, question: str, schema_context: str):

    prompt = f"""
You are an analytics reasoning engine.

Your job is to break a user question into analytical steps.

DATASET SCHEMA
{schema_context}

CRITICAL RULES:
1. Return ONLY a valid JSON ARRAY. No other text.
2. The outermost structure MUST be a JSON array [ ... ].
3. Do NOT wrap the array inside an object like {{"steps": [...]}}.
4. Do NOT nest a list inside the array, e.g. [{{}}, [...]] is WRONG.
5. Each element must have a "task" field.
6. If the question is simple, return a single-element array.

WRONG output (never do this):
{{"steps": [{{"step": 1, "task": "..."}}], "task": "..."}}

WRONG output (never do this either — nested list):
[{{}}, [{{"step": 1, "task": "..."}}]]

CORRECT output (always do this):
[
  {{
    "step": 1,
    "task": "aggregate revenue by dish",
    "metric": "Revenue",
    "dimension": "Dish"
  }}
]

User Question:
{question}
"""

    steps = await provider.generate_structured(prompt)

    logger.info(f"Raw decomposition output: {steps}")

    # Safety: if LLM still returns a dict despite instructions, unwrap it
    if isinstance(steps, dict):
        logger.warning("Decomposer returned dict instead of list, unwrapping")
        # Try to extract inner steps list
        if "steps" in steps and isinstance(steps["steps"], list):
            inner = steps["steps"]
            task  = steps.get("task", question)
            steps = []
            for s in inner:
                if isinstance(s, dict):
                    if "task" not in s:
                        s["task"] = task
                    steps.append(s)
        else:
            steps = [{"task": steps.get("task", question)}]

    if not isinstance(steps, list):
        logger.warning("Invalid decomposition output, fallback to single step")
        return [{"task": question}]

    # Flatten one level: LLM sometimes returns malformed shapes like
    # [{}, [{...}, {...}]] — a list containing a nested list of steps
    # instead of a flat array. Without this, the nested list gets
    # silently dropped by the "not isinstance(step, dict)" check below,
    # losing all the useful metric/dimension info it carried.
    flattened = []
    for item in steps:
        if isinstance(item, list):
            flattened.extend(item)
        else:
            flattened.append(item)

    # Ensure each step has a task; drop empty placeholder dicts
    cleaned_steps = []
    for step in flattened:
        if not isinstance(step, dict):
            continue
        if not step:  # empty {} carries no useful info — skip it
            continue
        if "task" not in step or not step["task"]:
            step["task"] = question
        cleaned_steps.append(step)

    if not cleaned_steps:
        cleaned_steps = [{"task": question}]

    logger.info(f"Final decomposition steps: {cleaned_steps}")

    return cleaned_steps
