import pandas as pd
from app.utils.code_executor import CodeExecutor
from fastapi import APIRouter
from app.services.llm.factory import get_llm_provider

router = APIRouter()
@router.get("/llm-test")
async def llm_test():

    provider = get_llm_provider()

    prompt = """
Dataset columns:
- Product (str)
- Sales (int)
- Country (str)

Question:
Top 5 products by sales and give insights.
"""

    llm_output = await provider.generate_structured(prompt)

    # Dummy dataframe
    df = pd.DataFrame({
        "Product": ["A","B","C","D","E","F"],
        "Sales": [100,200,150,80,60,300],
        "Country": ["India","India","China","China","Japan","Japan"]
    })

    execution_result = CodeExecutor.execute(
        llm_output["analysis_code"],
        df
    )

    return {
        "llm_output": llm_output,
        "execution_result": execution_result
    }