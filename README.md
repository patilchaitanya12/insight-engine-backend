# Insight Engine Backend

AI-powered analytics backend that converts natural language questions into data insights, charts, and tables.

This backend is built using **FastAPI**, integrates with an **LLM for analysis planning**, and safely executes generated **pandas transformations** to produce structured analytics results.

---

## Features

* Natural language data queries
* LLM-powered analytics engine
* Safe pandas execution environment
* Dataset upload API
* Automatic chart selection
* Insight generation
* Column hallucination correction
* Query validation and guardrails

---

## Architecture

User Query
↓
LLM Analysis Planner
↓
Pandas Code Generator
↓
Safe Execution Engine
↓
Chart Selector
↓
Insight Generator

---

## Tech Stack

* FastAPI
* Python
* Pandas
* MongoDB
* LLM integration
* Async APIs

---

## Project Structure

```
app/
│
├── api/
│   ├── upload.py
│   └── query.py
│
├── core/
│   └── database.py
│
├── services/
│   ├── llm/
│   └── insight_generator.py
│
├── utils/
│   ├── code_executor.py
│   ├── column_utils.py
│   └── chart_selector.py
│
└── main.py
```

---

## Installation

Clone the repository:

```
git clone <repo-url>
cd insight-engine-backend
```

Install dependencies:

```
uv sync
```

Run the server:

```
uv run uvicorn app.main:app --reload
```

Server runs at:

```
http://127.0.0.1:8000
```

---

## API Endpoints

### Upload Dataset

```
POST /upload/
```

Upload a CSV dataset for analysis.

---

### Query Dataset

```
POST /query/
```

Example request:

```
{
 "dataset_id": "uuid",
 "question": "Top 5 products by sales"
}
```

Example response:

```
{
 "table": {...},
 "chart": {...},
 "insights": "Top performing products by total sales."
}
```

---

## Future Improvements

* Query Planner for structured analytics planning
* Retrieval-Augmented Generation (RAG)
* Memory-aware analytics
* Multi-chart insights
* Dashboard analytics suggestions

---
