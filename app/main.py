from fastapi import FastAPI, HTTPException
import os
from openai import OpenAI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="MCQ Orchestrator Controller")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class TestRequest(BaseModel):
    prompt: str
    model: str = "gpt-3.5-turbo"

@app.get("/health")
async def health() -> dict:
    """Health check endpoint"""
    return {"status": "ok"}

@app.post("/test-openai")
async def test_openai(request: TestRequest):
    """Test endpoint to verify OpenAI integration"""
    try:
        response = client.chat.completions.create(
            model=request.model,
            messages=[{"role": "user", "content": request.prompt}]
        )
        return {"response": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Your existing imports and other endpoints...
from .models import FinalMCQ, GenerateRequest
from .orchestrator import run_generation_cycle

@app.post("/generate-mcq", response_model=FinalMCQ)
async def generate_mcq(req: GenerateRequest) -> FinalMCQ:
    try:
        return run_generation_cycle(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))