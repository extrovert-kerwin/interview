"""Parse a resume with local Python rules, without calling the LLM."""

from __future__ import annotations

import re

from app.agents.state import InterviewState

SKILL_KEYWORDS = [
    "Python", "Java", "C++", "Go", "TypeScript", "JavaScript", "React",
    "Next.js", "Vue", "FastAPI", "Django", "Flask", "Spring", "MySQL",
    "PostgreSQL", "Redis", "MongoDB", "Docker", "Kubernetes", "Linux",
    "LangChain", "LangGraph", "Agent", "RAG", "LLM", "LoRA", "Transformer",
    "PyTorch", "TensorFlow", "Milvus", "FAISS", "Elasticsearch", "Kafka",
]


def parse_resume(state: InterviewState) -> InterviewState:
    text = state.get("resume_text", "").strip()
    profile = build_profile(text)
    return {
        "resume_profile": profile,
        "target_total_questions": state.get("target_total_questions", 8),
        "stage": "planning",
        "last_active_agent": "InterviewAgent",
        "last_active_tool": "parse_resume",
    }


def build_profile(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "name": _extract_name(lines),
        "years_of_experience": _extract_years(text),
        "current_title": _extract_title(lines),
        "skills": _extract_skills(text),
        "projects": _extract_projects(lines),
        "highlights": _extract_highlights(lines),
    }


def _extract_name(lines: list[str]) -> str:
    for line in lines[:12]:
        match = re.search(r"(?:姓名|Name)[:：\s]*([\u4e00-\u9fa5A-Za-z·\s]{2,24})", line)
        if match:
            return match.group(1).strip()
    for line in lines[:5]:
        cleaned = re.sub(r"[\s|,，。:：/\\-]+", "", line)
        if 2 <= len(cleaned) <= 5 and re.fullmatch(r"[\u4e00-\u9fa5]{2,5}", cleaned):
            return cleaned
    return "候选人"


def _extract_years(text: str) -> float:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:年|yrs?|years?)\s*(?:经验|工作经验|experience)?",
        r"经验\s*[:：]?\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return 0


def _extract_title(lines: list[str]) -> str:
    title_words = ("工程师", "开发", "算法", "架构", "产品", "经理", "实习", "研究员")
    for line in lines[:20]:
        if any(word in line for word in title_words) and len(line) <= 40:
            return line
    return ""


def _extract_skills(text: str) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    for skill in SKILL_KEYWORDS:
        if skill.lower() in lowered and skill not in found:
            found.append(skill)
    return found[:12]


def _extract_projects(lines: list[str]) -> list[dict]:
    projects: list[dict] = []
    for i, line in enumerate(lines):
        if len(projects) >= 4:
            break
        if not any(token in line for token in ("项目", "系统", "平台", "Agent", "RAG", "推荐", "检索")):
            continue
        if len(line) < 6:
            continue
        context = " ".join(lines[i : i + 3])
        projects.append({
            "name": line[:40],
            "role": "",
            "highlight": context[:80],
        })
    return projects


def _extract_highlights(lines: list[str]) -> list[str]:
    scored: list[str] = []
    signal = ("提升", "降低", "优化", "负责", "主导", "实现", "%", "Top", "论文", "奖")
    for line in lines:
        if 12 <= len(line) <= 120 and any(word in line for word in signal):
            scored.append(line)
        if len(scored) >= 3:
            break
    return scored
