# -*- coding: utf-8 -*-
"""
modules/agents/roles.py
Auto-detect task type dan build agent yang tepat.
"""
import re
from .base import BaseAgent

# Keyword patterns untuk detect task type
_PATTERNS = {
    "coding": [
        r"\bcode\b", r"\bkode\b", r"\bscript\b", r"\bdebug\b", r"\bbug\b",
        r"\bfungsi\b", r"\bfunction\b", r"\bclass\b", r"\bpython\b",
        r"\bjavascript\b", r"\bhtml\b", r"\bcss\b", r"\bapi\b",
        r"\bprogram\b", r"\bimport\b", r"\bloop\b", r"\barray\b",
    ],
    "analysis": [
        r"\banalisa\b", r"\banalyze\b", r"\banalysis\b", r"\bdata\b",
        r"\bpola\b", r"\bpattern\b", r"\btrend\b", r"\bstatistik\b",
        r"\bgrafik\b", r"\bchart\b", r"\bperbandingan\b", r"\bcompare\b",
        r"\binsight\b", r"\bkorelas\b",
    ],
    "math": [
        r"\bhitung\b", r"\bcalculate\b", r"\bmatematika\b", r"\brumus\b",
        r"\bformula\b", r"\bpersamaan\b", r"\bequation\b", r"\bintegral\b",
        r"\bderivatif\b", r"\bprobabilitas\b", r"\bstatistika\b",
        r"\baljabar\b", r"\bgeometri\b", r"\bberapa\b",
    ],
    "research": [
        r"\briset\b", r"\bresearch\b", r"\bcari\b", r"\bsearch\b",
        r"\btentang\b", r"\bapa itu\b", r"\bwhat is\b", r"\bjelaskan\b",
        r"\bexplain\b", r"\binformasi\b", r"\bsejarah\b", r"\bhistory\b",
        r"\bsiapa\b", r"\bkapan\b", r"\bdimana\b",
    ],
    "writing": [
        r"\btulis\b", r"\bwrite\b", r"\bartikel\b", r"\bessay\b",
        r"\brangkum\b", r"\bsummariz\b", r"\bringkas\b", r"\bkonten\b",
        r"\bcontent\b", r"\bcerita\b", r"\bstory\b", r"\bdeskripsi\b",
        r"\bdescrib\b", r"\bsurat\b", r"\bletter\b", r"\bemail\b",
    ],
    "review": [
        r"\breview\b", r"\bcek\b", r"\bcheck\b", r"\bperiksa\b",
        r"\bkoreksi\b", r"\bcorrect\b", r"\bevaluat\b", r"\bkritik\b",
        r"\bkritisi\b", r"\bperbaiki\b", r"\bimprove\b", r"\bfeedback\b",
    ],
}


def detect_task_type(text: str) -> str:
    """Detect task type dari teks input. Returns task_type string."""
    text_lower = text.lower()
    scores = {k: 0 for k in _PATTERNS}
    for task_type, patterns in _PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                scores[task_type] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def build_team(task: str, keys: dict) -> dict:
    """
    Build agent team berdasarkan task.
    Returns dict of agents yang relevan.
    """
    task_type = detect_task_type(task)

    agents = {
        "orchestrator": BaseAgent(
            name="Orchestrator",
            role="Koordinator & Pengambil Keputusan",
            task_type="orchestrator",
            keys=keys,
        ),
        "primary": BaseAgent(
            name="Primary Agent",
            role=task_type.capitalize(),
            task_type=task_type,
            keys=keys,
        ),
        "critic": BaseAgent(
            name="Critic",
            role="Reviewer & Quality Control",
            task_type="critic",
            keys=keys,
        ),
    }

    # Tambah secondary agent jika task butuh perspektif berbeda
    secondary_map = {
        "coding":   "review",
        "analysis": "research",
        "writing":  "review",
        "research": "analysis",
        "math":     "review",
    }
    secondary_type = secondary_map.get(task_type)
    if secondary_type:
        agents["secondary"] = BaseAgent(
            name="Secondary Agent",
            role=secondary_type.capitalize(),
            task_type=secondary_type,
            keys=keys,
        )

    return agents, task_type


def auto_select_agent(task: str, keys: dict) -> BaseAgent:
    """Buat single agent terbaik untuk task ini."""
    task_type = detect_task_type(task)
    return BaseAgent(
        name="Auto Agent",
        role=task_type.capitalize(),
        task_type=task_type,
        keys=keys,
    )
