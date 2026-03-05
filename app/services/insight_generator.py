async def generate_insights(provider, result_df, question):

    table_preview = result_df.head(10).to_string(index=False)

    prompt = f"""
You are a data analyst.

The user asked:
{question}

Here is the result table:

{table_preview}

Write 2-3 short insights describing the key findings.
Mention actual values from the table.
"""

    response = await provider.generate_text(prompt)

    return response