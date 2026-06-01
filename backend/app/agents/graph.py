"""Single-agent orchestration for the interview flow.

The public API still exposes setup_graph / continue_graph / finalize_graph with
an .invoke(state) method so the route layer does not need to know whether the
implementation is LangGraph or a lighter local orchestrator.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.agents.evaluator import evaluate
from app.agents.follow_up import judge_follow_up
from app.agents.interviewer import ask_question
from app.agents.question_planner import plan_questions
from app.agents.reporter import build_report
from app.agents.resume_parser import parse_resume
from app.agents.state import InterviewState

Tool = Callable[[InterviewState], InterviewState]


class InterviewAgent:
    """One agent that owns the interview workflow and calls local tools."""

    name = "InterviewAgent"

    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {
            "parse_resume": parse_resume,
            "plan_questions": plan_questions,
            "ask_question": ask_question,
            "judge_follow_up": judge_follow_up,
            "evaluate": evaluate,
            "build_report": build_report,
        }

    def run_tools(self, state: InterviewState, tool_names: list[str]) -> InterviewState:
        current: InterviewState = dict(state)
        for tool_name in tool_names:
            update = self.tools[tool_name](current)
            current.update(update)
            current["last_active_agent"] = self.name
            current["last_active_tool"] = tool_name
        return current


@dataclass(frozen=True)
class AgentPhase:
    agent: InterviewAgent
    tool_names: list[str]
    mode: Literal["setup", "continue", "finalize"] = "setup"

    def invoke(self, state: InterviewState) -> InterviewState:
        if self.mode == "continue":
            current = self.agent.run_tools(state, ["judge_follow_up"])
            if current.get("stage") == "evaluating" or current.get("pending_question"):
                return current
            return self.agent.run_tools(current, ["plan_questions", "ask_question"])
        return self.agent.run_tools(state, self.tool_names)


interview_agent = InterviewAgent()

setup_graph = AgentPhase(
    interview_agent,
    ["parse_resume", "plan_questions", "ask_question"],
)
continue_graph = AgentPhase(
    interview_agent,
    ["judge_follow_up", "ask_question"],
    mode="continue",
)
finalize_graph = AgentPhase(
    interview_agent,
    ["evaluate", "build_report"],
    mode="finalize",
)
next_question_graph = AgentPhase(
    interview_agent,
    ["plan_questions", "ask_question"],
)


def agent_pipeline() -> list[str]:
    """Frontend timeline: show a single agent with multiple tools."""
    return [interview_agent.name]
