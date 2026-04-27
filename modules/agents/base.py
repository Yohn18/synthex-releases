# -*- coding: utf-8 -*-
"""
modules/agents/base.py
BaseAgent — unit dasar setiap AI agent dalam team.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from .providers import call_with_fallback


@dataclass
class AgentMessage:
    sender:   str
    content:  str
    msg_type: str  # task | response | review | discuss | final | system
    metadata: dict = field(default_factory=dict)


class BaseAgent:
    def __init__(self, name: str, role: str, task_type: str,
                 keys: dict, system_prompt: str = ""):
        self.name      = name
        self.role      = role
        self.task_type = task_type
        self.keys      = keys
        self.system    = system_prompt or self._default_system()
        self._history: List[dict] = []
        self.last_model_used = ""

    def _default_system(self) -> str:
        defaults = {
            "orchestrator": (
                "Kamu adalah Orchestrator AI. Tugasmu: analisa task, pecah menjadi subtask, "
                "tentukan agent mana yang paling tepat, koordinasi diskusi antar agent, "
                "dan buat output final yang komprehensif. "
                "Selalu gunakan Bahasa Indonesia kecuali diminta lain."
            ),
            "coding": (
                "Kamu adalah Coder AI spesialis. Tulis kode yang bersih, efisien, dan berikan "
                "penjelasan singkat. Prioritaskan solusi yang langsung bisa dijalankan."
            ),
            "analysis": (
                "Kamu adalah Analyst AI. Analisa data, temukan pola, berikan insight mendalam "
                "dengan logika yang kuat dan terstruktur."
            ),
            "research": (
                "Kamu adalah Researcher AI. Cari informasi akurat, rangkum dengan jelas, "
                "dan selalu sertakan konteks yang relevan."
            ),
            "writing": (
                "Kamu adalah Writer AI. Tulis konten yang jelas, menarik, dan sesuai konteks. "
                "Perhatikan struktur, alur, dan keterbacaan."
            ),
            "math": (
                "Kamu adalah Math AI. Selesaikan masalah matematika dan logika secara sistematis, "
                "tunjukkan langkah-langkah secara jelas."
            ),
            "review": (
                "Kamu adalah Critic AI. Review output agent lain secara objektif, "
                "temukan kelemahan, dan berikan saran perbaikan yang konstruktif."
            ),
            "general": (
                "Kamu adalah AI serba bisa. Jawab dengan akurat, jelas, dan ringkas."
            ),
        }
        return defaults.get(self.task_type, defaults["general"])

    def think(self, task: str, context: str = "",
              stream_cb=None, max_tokens: int = 2048) -> AgentMessage:
        messages = [{"role": "system", "content": self.system}]
        for h in self._history[-6:]:  # max 6 history untuk hemat token
            messages.append(h)
        if context:
            messages.append({
                "role": "user",
                "content": "[KONTEKS DARI AGENT LAIN]\n{}\n\n[TASK]\n{}".format(context, task)
            })
        else:
            messages.append({"role": "user", "content": task})

        text, label = call_with_fallback(
            self.task_type, messages, self.keys,
            max_tokens=max_tokens, stream_cb=stream_cb
        )
        self.last_model_used = label
        self._history.append({"role": "user",    "content": task})
        self._history.append({"role": "assistant", "content": text})

        return AgentMessage(
            sender=self.name,
            content=text,
            msg_type="response",
            metadata={"model": label, "role": self.role}
        )

    def discuss(self, topic: str, other_response: str,
                stream_cb=None) -> AgentMessage:
        prompt = (
            "Agent lain memberikan respons berikut:\n\n"
            "{}\n\n"
            "Apakah kamu setuju? Jika tidak, berikan argumen yang lebih baik. "
            "Jika setuju, perkuat dengan tambahan. Topik: {}"
        ).format(other_response, topic)
        return self.think(prompt, stream_cb=stream_cb, max_tokens=1024)

    def reset_history(self):
        self._history.clear()
