from fastapi import FastAPI

app = FastAPI(
    title="Insight Engine",
    version="0.1.0",
    description="LLM-powered analytics backend"
)

@app.get("/health")
def health_check():
    return {"status": "ok"}