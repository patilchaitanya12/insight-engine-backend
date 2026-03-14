
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
        You are a senior data analyst writing pandas transformations.
        
        STRICT RULES:
        
        1. Assume a pandas DataFrame named df already exists.
        2. Do not import any libraries.
        3. The final output must be assigned to variable named result.
        4. result must be a pandas DataFrame.
        5. Prefer the simplest pandas transformation that answers the question.
        6. Avoid unnecessary groupby, merge, or joins unless explicitly required.
        7. When selecting top N within groups, use:
           groupby(...).sum().reset_index().sort_values(...).groupby(...).head(N)
           Do NOT use nlargest(level=...)
        
        Return ONLY valid JSON.
        
        Format:
        
        {
         "analysis_code": "pandas code assigning to result",
         "chart_type": "bar | line | pie | scatter",
         "x_column": "column name",
         "y_column": "column name",
         "insights": "short business insight"
        }
        
        Example:
        
        User Question:
        Top 5 products country wise
        
        Correct Response:
        
        {
         "analysis_code": "result = df.groupby(['Country','Product'])['Sales'].sum().reset_index().sort_values(['Country','Sales'], ascending=[True, False]).groupby('Country').head(5)",
         "chart_type": "bar",
         "x_column": "Product",
         "y_column": "Sales",
         "insights": "This shows the top performing products within each country."
        }
        """
        
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            response_format={"type": "json_object"},
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
            return {
                "analysis_code": "result = df.head()",
                "chart_type": "bar",
                "x_column": "",
                "y_column": "",
                "insights": "Model returned invalid JSON. Fallback used."
            }
    
    async def generate_text(self, prompt: str) -> str:

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful data analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        content = response.choices[0].message.content

        if content:
            content = content.replace("```json", "").replace("```", "").strip()

        return content or ""
