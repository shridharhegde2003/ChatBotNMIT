import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable must be set.")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SOLVER_A_URL = os.getenv("SOLVER_A_URL", "http://localhost:5678/webhook-solver-a")
SOLVER_B_URL = os.getenv("SOLVER_B_URL", "http://localhost:5678/webhook-solver-b")

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

config_list = [
    {
        "model": OPENAI_MODEL,
        "api_key": OPENAI_API_KEY,
    }
]

llm_config = {
    "config_list": config_list,
    "temperature": 0.2,
}
