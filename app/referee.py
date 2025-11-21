import json
from typing import Optional

import autogen

from .config import llm_config
from .models import MCQQuestion, RefereeDecision, SolverResult
 

def _build_initial_prompt(
    mcq: MCQQuestion,
    sol_a: SolverResult,
    sol_b: SolverResult,
    controller_result: Optional[SolverResult] = None,
) -> str:
    text = (
        "You are a group of agents: Referee, SolverAAgent, SolverBAgent, and optionally ControllerAgent. "
        "You are given a quantitative MCQ and up to three solver outputs. "
        "Your goal is to agree on a single numeric answer with the correct unit and then help Referee map it to an option or indicate that options must be updated.\n\n"
        "Problem:\n"
        f"Question: {mcq.question}\n"
        f"Options:\n" + "\n".join(mcq.options) + "\n\n"
        "Required unit (if any): "
        f"{mcq.meta.required_unit or 'none specified'}\n\n"
        "Solver A output (JSON):\n" + json.dumps(sol_a.dict(), indent=2) + "\n\n"
        "Solver B output (JSON):\n" + json.dumps(sol_b.dict(), indent=2) + "\n\n"
    )

    if controller_result is not None:
        text += (
            "Controller solver output (JSON):\n"
            + json.dumps(controller_result.dict(), indent=2)
            + "\n\n"
        )

    text += (
        "Discussion instructions:\n"
        "- SolverAAgent, SolverBAgent, and ControllerAgent (if present) should briefly defend or reconsider their prior answers.\n"
        "- Referee should ask clarification questions if needed.\n"
        "- All agents must ensure strict unit correctness.\n"
        "- The final numeric answer must be consistent with the story and realistic.\n"
        "- If no option currently matches the correct numeric answer, Referee may still ACCEPT but note that options need to be updated.\n\n"
        "Final output format (Referee only):\n"
        "Referee MUST finish the conversation with a single message that is PURE JSON, no backticks, no extra text, of the form:\n"
        "{\n"
        "  \"status\": \"accepted\" or \"reject_and_regenerate\",\n"
        "  \"final_value\": {\"value\": <float>, \"unit\": \"<unit>\"} or null,\n"
        "  \"selected_option\": \"A\"/\"B\"/\"C\"/\"D\" or null,\n"
        "  \"explanation\": \"short explanation of the decision, including whether options need updating\"\n"
        "}\n"
        "If the question is flawed or no consistent answer can be reached, use status = \"reject_and_regenerate\" and set final_value and selected_option to null."
    )

    return text

def run_referee_groupchat(
    mcq: MCQQuestion,
    sol_a: SolverResult,
    sol_b: SolverResult,
    controller_result: Optional[SolverResult] = None,
) -> RefereeDecision:
    """Run an AutoGen GroupChat to reconcile solver disagreements.

    Returns a RefereeDecision with status either 'accepted' or 'reject_and_regenerate'.
    """

    referee = autogen.AssistantAgent(
        name="Referee",
        system_message=(
            "You are the strict mathematical referee. "
            "You must ensure the final answer is mathematically correct, uses the required unit, "
            "and corresponds to exactly one of the options. "
            "At the end of the discussion, you MUST output exactly one JSON object as specified, "
            "with no additional commentary."
        ),
        llm_config=llm_config,
    )

    solver_a_agent = autogen.AssistantAgent(
        name="SolverAAgent",
        system_message=(
            "You represent Solver A. You are given Solver A's prior numeric answer and reasoning. "
            "You may adjust your answer if you are convinced by arguments, but you do NOT output the final JSON."
        ),
        llm_config=llm_config,
    )

    solver_b_agent = autogen.AssistantAgent(
        name="SolverBAgent",
        system_message=(
            "You represent Solver B. You are given Solver B's prior numeric answer and reasoning. "
            "You may adjust your answer if you are convinced by arguments, but you do NOT output the final JSON."
        ),
        llm_config=llm_config,
    )

    controller_agent = autogen.AssistantAgent(
        name="ControllerAgent",
        system_message=(
            "You represent the orchestrator's internal controller solver. "
            "You are given the controller's prior numeric answer and reasoning. "
            "You may adjust your answer if you are convinced by arguments, but you do NOT output the final JSON."
        ),
        llm_config=llm_config,
    )

    user_proxy = autogen.UserProxyAgent(
        name="User",
        system_message=(
            "You only provide the task description and do not solve it yourself. "
            "Let the agents discuss and let Referee output the final JSON decision."
        ),
        code_execution_config={"use_docker": False},
    )

    agents = [user_proxy, referee, solver_a_agent, solver_b_agent]
    if controller_result is not None:
        agents.append(controller_agent)

    groupchat = autogen.GroupChat(
        agents=agents,
        messages=[],
        max_round=6,
    )

    manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=llm_config)

    initial_prompt = _build_initial_prompt(mcq, sol_a, sol_b, controller_result)
    user_proxy.initiate_chat(manager, message=initial_prompt)

    # Find the last message from Referee and parse as JSON
    last_ref_content: Optional[str] = None
    for msg in reversed(groupchat.messages):
        if msg.get("name") == "Referee":
            last_ref_content = msg.get("content", "")
            break

    if not last_ref_content:
        raise RuntimeError("No final message from Referee in group chat.")

    try:
        data = json.loads(last_ref_content)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Failed to parse Referee JSON decision: {exc}. Content was: {last_ref_content!r}"
        ) from exc

    return RefereeDecision(**data)
