async def generate_insights(provider, result_df, question):

    if result_df.empty:
        return "No meaningful results were produced from the query."

    # Preview rows
    preview = result_df.head(8).to_string(index=False)

    # Detect numeric columns
    numeric_cols = result_df.select_dtypes(include=["number"]).columns.tolist()

    # Generate statistics safely
    stats = ""
    if numeric_cols:

        stat_lines = []

        for col in numeric_cols[:2]:  # limit to first 2 metrics
            try:
                stat_lines.append(
                    f"{col} → max: {result_df[col].max()}, "
                    f"min: {result_df[col].min()}, "
                    f"avg: {round(result_df[col].mean(), 2)}"
                )
            except Exception:
                continue

        stats = "\n".join(stat_lines)

    # Column awareness (prevents hallucination)
    columns = ", ".join(result_df.columns.tolist())

    prompt = f"""
You are a senior data analyst.

User Question:
{question}

Available Columns:
{columns}

Result Preview:
{preview}

Summary Statistics:
{stats}

STRICT RULES:
1. Only use the columns listed in "Available Columns".
2. Do NOT invent new columns or metrics.
3. Base insights strictly on the result preview and statistics.
4. Mention real values when possible.
5. Write 2–3 concise insights.

Return plain text insights only.
"""

    response = await provider.generate_text(prompt)

    return response.strip()
