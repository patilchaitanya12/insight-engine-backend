import json
from typing import Dict, Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.llm.base import LLMProvider


class GenericLLMProvider(LLMProvider):

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL
        )
        self.model = settings.LLM_MODEL

    async def generate_structured(self, prompt: str) -> Dict[str, Any]:

        system_prompt = """
        You are a senior data analyst.
        
        IMPORTANT RULES:
        1. Do NOT import any libraries.
        2. Do NOT generate plotting code.
        3. Only write pandas transformation code.
        4. The final output MUST be assigned to variable named 'result'.
        5. Assume a pandas DataFrame named 'df' already exists.
        6. Return ONLY valid JSON.
        7. No markdown.
        8. No explanation.
        
        Return strictly this format:
        
        {
          "analysis_code": "pandas code only",
          "chart_type": "bar | line | pie | scatter",
          "x_column": "column_name",
          "y_column": "column_name",
          "insights": "clear business insight explanation"
        }
        """

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )

        raw_output = response.choices[0].message.content

        return self._safe_parse(raw_output)

    def _safe_parse(self, raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # fallback minimal safe structure
            return {
                "analysis_code": "result = df.head()",
                "chart_type": "bar",
                "x_column": "",
                "y_column": "",
                "insights": "Model returned invalid JSON. Fallback used."
            }