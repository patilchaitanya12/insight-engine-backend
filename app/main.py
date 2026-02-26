from fastapi import FastAPI
from app.api import test_llm
from app.api import upload
from app.api import query

app = FastAPI(
    title="Insight Engine",
    version="0.1.0",
    description="LLM-powered analytics backend"
)

app.include_router(test_llm.router, prefix="/test")
app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(query.router, prefix="/query", tags=["Query"])

@app.get("/health")
def health_check():
    return {"status": "ok"}