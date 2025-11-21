import json
from typing import Tuple

import autogen
import requests

from .config import MAX_RETRIES, SOLVER_A_URL, SOLVER_B_URL, llm_config
from .models import FinalMCQ, GenerateRequest, MCQMeta, MCQQuestion, SolverResult
from .referee import run_referee_groupchat
from .utils import (
    combine_derivation,
    ensure_option_contains_answer,
    generate_question_id,
    unit_matches,
    values_equal,
)


problem_generator = autogen.AssistantAgent(
    name="ProblemGenerator",
    system_message=(
        "You generate quantitative, scenario-based MCQ word problems. "
        "Always return EXACTLY one JSON object, no prose, with fields: \n"
        "- question: string (problem statement)\n"
        "- options: array of 4 strings labelled like 'A. ...', 'B. ...', 'C. ...', 'D. ...'\n"
        "- meta: {topic, difficulty, required_unit, correct_option_internal, correct_value:{value,unit}}\n"
        "Constraints:\n"
        "- The correct_value must be a single numeric answer with the exact unit = required_unit.\n"
        "- One and only one option must contain this numeric value and unit.\n"
        "- The scenario must be realistic (no negative time, impossible speeds, etc.)."
    ),
    llm_config=llm_config,
)


controller_solver = autogen.AssistantAgent(
    name="ControllerSolver",
    system_message=(
        "You are the orchestrator's internal controller solver for quantitative MCQs. "
        "Given a word problem and four options, you MUST solve it carefully using precise math. "
        "Always return EXACTLY one JSON object, no prose, with fields: \n"
        "- final_value: {value: <float>, unit: '<unit>'} (use the required unit if specified)\n"
        "- selected_option: 'A' | 'B' | 'C' | 'D' (the best matching choice, if any)\n"
        "- reasoning: string (step-by-step explanation)\n"
        "- confidence: float between 0 and 1.\n"
        "If no option matches the correct numeric answer, still output the correct final_value and set selected_option to the closest or null."
    ),
    llm_config=llm_config,
)


def _generate_mcq_once(req: GenerateRequest, attempt: int) -> MCQQuestion:
    """Call the ProblemGenerator once and parse the MCQ JSON."""
    prompt = (
        f"Generate one quantitative MCQ for the topic: {req.topic}.\n"
        f"Difficulty: {req.difficulty}. Required unit: {req.required_unit}.\n"
        "Return ONLY the JSON object, no extra text."
    )

    reply = problem_generator.generate_reply(
        messages=[{"role": "user", "content": prompt}]
    )

    if isinstance(reply, dict):
        data = reply
    else:
        data = json.loads(str(reply))

    # Ensure meta exists and fill defaults
    if "meta" not in data:
        data["meta"] = {}

    meta = data["meta"]
    meta.setdefault("topic", req.topic)
    meta.setdefault("difficulty", req.difficulty)
    meta.setdefault("required_unit", req.required_unit)

    mcq = MCQQuestion(**data)

    if not mcq.question_id:
        mcq.question_id = generate_question_id(req.topic)

    # Basic validation
    if len(mcq.options) != 4:
        raise ValueError("Generator must return exactly 4 options.")
    if not mcq.meta.correct_value or not mcq.meta.correct_option_internal:
        raise ValueError("Generator meta must include correct_value and correct_option_internal.")

    return mcq


def _solve_with_controller(mcq: MCQQuestion) -> SolverResult:
    """Solve the MCQ using the controller's own solver agent."""

    required_unit = mcq.meta.required_unit or "none specified"
    options_text = "\n".join(mcq.options)
    prompt = (
        "You are given a quantitative MCQ. Solve it carefully.\n"
        f"Required unit: {required_unit}.\n"
        "Return ONLY the JSON object, no extra text.\n\n"
        f"Question: {mcq.question}\n\n"
        f"Options:\n{options_text}"
    )

    reply = controller_solver.generate_reply(
        messages=[{"role": "user", "content": prompt}]
    )

    if isinstance(reply, dict):
        data = reply
    else:
        data = json.loads(str(reply))

    data.setdefault("solver_id", "Controller")
    data.setdefault("question_id", mcq.question_id)

    return SolverResult(**data)


def _call_solver(url: str, solver_id: str, mcq: MCQQuestion) -> SolverResult:
    payload = mcq.dict()
    resp = requests.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    data.setdefault("solver_id", solver_id)
    return SolverResult(**data)


def _is_perfect_match(mcq: MCQQuestion, sol_a: SolverResult, sol_b: SolverResult) -> Tuple[bool, str]:
    meta: MCQMeta = mcq.meta
    correct = meta.correct_value
    if not correct:
        return False, "Missing correct_value in meta."

    required_unit = meta.required_unit

    if not (
        unit_matches(sol_a.final_value, required_unit)
        and unit_matches(sol_b.final_value, required_unit)
        and unit_matches(correct, required_unit)
    ):
        return False, "Unit mismatch between solvers and/or correct value."

    if not (
        values_equal(sol_a.final_value, sol_b.final_value)
        and values_equal(sol_a.final_value, correct)
    ):
        return False, "Numeric mismatch between solvers and/or correct value."

    if not (
        sol_a.selected_option
        and sol_b.selected_option
        and meta.correct_option_internal
    ):
        return False, "Missing selected_option or correct_option_internal."

    if not (
        sol_a.selected_option == sol_b.selected_option == meta.correct_option_internal
    ):
        return False, "Option letter mismatch between solvers and meta."

    return True, "Perfect match."


def run_generation_cycle(req: GenerateRequest) -> FinalMCQ:
    """Generate, solve, possibly reconcile, and return a validated MCQ.

    May retry up to MAX_RETRIES times if inconsistencies arise.
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            mcq = _generate_mcq_once(req, attempt)
        except Exception as exc:  # noqa: BLE001
            last_error = f"Generator error on attempt {attempt}: {exc}"
            continue

        # Call solvers via n8n webhooks
        try:
            sol_a = _call_solver(SOLVER_A_URL, "A", mcq)
            sol_b = _call_solver(SOLVER_B_URL, "B", mcq)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Error calling solvers: {exc}") from exc

        ok, reason = _is_perfect_match(mcq, sol_a, sol_b)
        if ok:
            derivation = combine_derivation(mcq, sol_a, sol_b)
            return FinalMCQ(
                question=mcq.question,
                options=mcq.options,
                answer=mcq.meta.correct_option_internal or sol_a.selected_option or "",
                answer_value=mcq.meta.correct_value or sol_a.final_value,
                derivation=derivation,
                topic=mcq.meta.topic or req.topic,
                difficulty=mcq.meta.difficulty or req.difficulty,
            )

        # Otherwise, have the controller also solve the question, then use Referee group chat
        try:
            controller_result = _solve_with_controller(mcq)
        except Exception as exc:  # noqa: BLE001
            controller_result = None
            last_error = f"Controller solver failed on attempt {attempt}: {exc}"

        try:
            decision = run_referee_groupchat(mcq, sol_a, sol_b, controller_result)
        except Exception as exc:  # noqa: BLE001
            last_error = f"Referee group chat failed on attempt {attempt}: {exc}"
            continue

        if (
            decision.status == "accepted"
            and decision.final_value is not None
        ):
            # Ensure unit matches required unit if specified
            if not unit_matches(decision.final_value, mcq.meta.required_unit):
                last_error = "Referee final value unit does not match required unit."
                continue

            # Adjust options so that one choice explicitly matches the final numeric answer + unit
            adjusted_options, final_letter, changed = ensure_option_contains_answer(
                mcq.options,
                preferred_letter=decision.selected_option,
                value=decision.final_value,
            )

            consensus_note = "Final answer agreed by Solver A, Solver B, controller, and Referee."
            options_note = None
            if changed:
                options_note = (
                    "Options were adjusted by the orchestrator so that one choice "
                    "contains the agreed correct numeric answer with the required unit."
                )

            derivation = combine_derivation(
                mcq,
                sol_a,
                sol_b,
                controller_result=controller_result,
                referee_explanation=decision.explanation,
                consensus_note=consensus_note,
                options_note=options_note,
            )

            return FinalMCQ(
                question=mcq.question,
                options=adjusted_options,
                answer=final_letter,
                answer_value=decision.final_value,
                derivation=derivation,
                topic=mcq.meta.topic or req.topic,
                difficulty=mcq.meta.difficulty or req.difficulty,
            )

        # If referee requested regeneration, just move to next attempt
        last_error = f"Referee requested regeneration on attempt {attempt}: {decision.explanation}"

    raise RuntimeError(
        f"Failed to produce a valid MCQ after {MAX_RETRIES} attempts. Last error: {last_error}"
    )
