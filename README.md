# MCQ Orchestrator Controller (AutoGen + n8n)

This service acts as the **controller/orchestrator** between your n8n workflows and multiple solver agents. It:

- Receives a **topic** and constraints from n8n (front end).
- Uses **AutoGen** to generate a quantitative, scenario-based MCQ.
- Sends the MCQ to **Solver A** and **Solver B** (implemented as n8n workflows).
- Compares their answers and units.
- If needed, runs a **Referee group chat** to resolve disagreements.
- Returns a final, validated MCQ JSON back to n8n (output workflow).

## 1. Setup

1. Create and activate a Python virtual environment (optional but recommended).
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Set environment variables:

   - `OPENAI_API_KEY` – your OpenAI key used by AutoGen.
   - `OPENAI_MODEL` – model name (default: `gpt-4o-mini`).
   - `SOLVER_A_URL` – n8n webhook URL for Solver A.
   - `SOLVER_B_URL` – n8n webhook URL for Solver B.
   - `MAX_RETRIES` – (optional) number of regenerate attempts, default `3`.

## 2. Run the controller API

From the project root:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Health check: `GET /health`
- Main endpoint: `POST /generate-mcq`

## 3. Request and response schemas

### 3.1 Front-end → Controller (`POST /generate-mcq`)

```json
{
  "topic": "relative speed and trains",
  "difficulty": "medium",
  "num_questions": 1,
  "required_unit": "m/s"
}
```

### 3.2 Controller → Solver A/B (payload sent to n8n webhooks)

```json
{
  "question_id": "train_001",
  "question": "A train ... ?",
  "options": ["A. 10 m/s", "B. 15 m/s", "C. 18 m/s", "D. 20 m/s"],
  "meta": {
    "topic": "relative speed",
    "difficulty": "medium",
    "required_unit": "m/s",
    "correct_option_internal": "B",
    "correct_value": {"value": 15, "unit": "m/s"}
  }
}
```

### 3.3 Solver A/B → Controller (n8n webhook response)

```json
{
  "solver_id": "A",
  "question_id": "train_001",
  "final_value": {"value": 15, "unit": "m/s"},
  "selected_option": "B",
  "reasoning": "Algebraic steps...",
  "confidence": 0.92
}
```

### 3.4 Controller → Output workflow (final validated MCQ)

```json
{
  "question": "A train ... ?",
  "options": ["A. 10 m/s", "B. 15 m/s", "C. 18 m/s", "D. 20 m/s"],
  "answer": "B",
  "answer_value": {"value": 15, "unit": "m/s"},
  "derivation": "hidden reasoning from generator and solvers",
  "topic": "relative speed",
  "difficulty": "medium"
}
```

## 4. n8n integration

- **Front-end workflow**: collects topic/difficulty/unit, calls `POST /generate-mcq`, and passes the response to your output node.
- **Solver A/B workflows**: expose webhooks that accept the MCQ JSON above, solve it (with your own LLM nodes), and respond with the SolverResult JSON.
- **Output workflow**: receives the final MCQ JSON and posts it to Google Forms, HTML quiz, etc.

The controller service handles AutoGen orchestration, Referee group chat, consistency checks, and unit-aligned validation.
