from fastapi import FastAPI
from app.api import test_llm
from app.api import upload
from app.api import query
from fastapi.middleware.cors import CORSMiddleware

import logging

app = FastAPI(
    title="Insight Engine",
    version="0.1.0",
    description="LLM-powered analytics backend"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(test_llm.router, prefix="/test")
app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(query.router, prefix="/query", tags=["Query"])

@app.get("/health")
def health_check():
    return {"status": "ok"}
    
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

@app.get("/")
def root():
    return {
        "message": "Welcome to Insight Engine API",
        "description": "AI-powered analytics backend",
        "version": "0.1.0",
        "docs": "/docs"
    }