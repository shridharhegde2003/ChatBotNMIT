from typing import List, Optional, Literal

from pydantic import BaseModel


class ValueWithUnit(BaseModel):
    value: float
    unit: str


class MCQMeta(BaseModel):
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    required_unit: Optional[str] = None
    correct_option_internal: Optional[str] = None
    correct_value: Optional[ValueWithUnit] = None


class MCQQuestion(BaseModel):
    question_id: Optional[str] = None
    question: str
    options: List[str]
    meta: MCQMeta


class GenerateRequest(BaseModel):
    topic: str
    difficulty: str = "medium"
    num_questions: int = 1
    required_unit: str = "m/s"


class SolverResult(BaseModel):
    solver_id: str
    question_id: Optional[str] = None
    final_value: ValueWithUnit
    selected_option: Optional[str] = None
    reasoning: str
    confidence: Optional[float] = None


class FinalMCQ(BaseModel):
    question: str
    options: List[str]
    answer: str
    answer_value: ValueWithUnit
    derivation: str
    topic: str
    difficulty: Optional[str] = None


class RefereeDecision(BaseModel):
    status: Literal["accepted", "reject_and_regenerate"]
    final_value: Optional[ValueWithUnit] = None
    selected_option: Optional[str] = None
    explanation: Optional[str] = None
