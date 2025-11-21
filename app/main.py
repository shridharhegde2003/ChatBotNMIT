from fastapi import FastAPI, HTTPException

from .models import FinalMCQ, GenerateRequest
from .orchestrator import run_generation_cycle


app = FastAPI(title="MCQ Orchestrator Controller")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/generate-mcq", response_model=FinalMCQ)
async def generate_mcq(req: GenerateRequest) -> FinalMCQ:
    try:
        return run_generation_cycle(req)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
