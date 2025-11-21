import re
import uuid
from typing import Optional

from .models import MCQQuestion, SolverResult, ValueWithUnit


def generate_question_id(topic: str) -> str:
    """Generate a reasonably unique question id based on topic."""
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-") or "q"
    return f"{slug}-{uuid.uuid4().hex[:8]}"


def values_equal(v1: ValueWithUnit, v2: ValueWithUnit, tol: float = 1e-6) -> bool:
    """Numeric + unit equality with small tolerance."""
    if v1.unit.strip().lower() != v2.unit.strip().lower():
        return False
    return abs(v1.value - v2.value) <= tol


def unit_matches(v: ValueWithUnit, required_unit: Optional[str]) -> bool:
    if not required_unit:
        return True
    return v.unit.strip().lower() == required_unit.strip().lower()


def _format_value_with_unit(value: ValueWithUnit) -> str:
    return f"{value.value:g} {value.unit}"


def ensure_option_contains_answer(
    options: list[str],
    preferred_letter: Optional[str],
    value: ValueWithUnit,
) -> tuple[list[str], str, bool]:
    """Ensure one option explicitly states the correct value + unit.

    Returns (updated_options, final_letter, changed_flag).
    """

    if not options:
        return [f"A. {_format_value_with_unit(value)}"], "A", True

    letter = (preferred_letter or "A").strip().upper()
    target_text = f"{letter}. {_format_value_with_unit(value)}"

    updated = []
    replaced = False
    for opt in options:
        prefix = opt.split(".", 1)[0].strip().upper()
        if prefix == letter:
            if opt.strip() == target_text:
                updated.append(opt)
            else:
                updated.append(target_text)
                replaced = True
        else:
            updated.append(opt)

    if not any(opt.split(".", 1)[0].strip().upper() == letter for opt in options):
        # Forcefully replace the first option to keep exactly 4 entries.
        updated[0] = f"A. {_format_value_with_unit(value)}"
        letter = "A"
        replaced = True

    return updated, letter, replaced


def option_contains_value(option_text: str, value: ValueWithUnit) -> bool:
    text = option_text.lower()
    value_str = f"{value.value:g}".lower()
    unit_str = value.unit.strip().lower()
    return value_str in text and unit_str in text


def combine_derivation(
    mcq: MCQQuestion,
    sol_a: SolverResult,
    sol_b: SolverResult,
    controller_result: Optional[SolverResult] = None,
    referee_explanation: Optional[str] = None,
    consensus_note: Optional[str] = None,
    options_note: Optional[str] = None,
) -> str:
    parts = []
    parts.append("Problem:\n" + mcq.question)
    parts.append("\nOptions:\n" + "\n".join(mcq.options))
    parts.append("\nSolver A reasoning:\n" + sol_a.reasoning)
    parts.append("\nSolver B reasoning:\n" + sol_b.reasoning)
    if controller_result:
        parts.append("\nController solver reasoning:\n" + controller_result.reasoning)
    if consensus_note:
        parts.append("\nConsensus note:\n" + consensus_note)
    if referee_explanation:
        parts.append("\nReferee explanation:\n" + referee_explanation)
    if options_note:
        parts.append("\nOption adjustment:\n" + options_note)
    return "\n".join(parts)
