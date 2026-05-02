# -*- coding: utf-8 -*-
"""
modules/agents/team.py
AgentTeam — orchestrator multi-agent dengan diskusi & review.
"""
import threading
from .roles import build_team, detect_task_type
from .memory import AgentMemory


class AgentTeam:
    def __init__(self, keys: dict, stream_cb=None, log_cb=None):
        """
        keys    = {"groq": "...", "together": "...", "openrouter": "..."}
        stream_cb(text)  — dipanggil setiap ada token baru (streaming)
        log_cb(msg)      — dipanggil untuk status update (e.g. "Orchestrator berpikir...")
        """
        self.keys      = keys
        self.stream_cb = stream_cb
        self.log_cb    = log_cb or (lambda msg: None)
        self.memory    = AgentMemory()

    def _log(self, msg: str):
        self.log_cb(msg)

    def run(self, task: str, max_tokens: int = 2048) -> dict:
        """
        Jalankan full agent pipeline untuk satu task.
        Returns dict: {result, session_id, task_type, agents_used, discussion}
        """
        session_id = self.memory.new_session(task)
        agents, task_type = build_team(task, self.keys)

        self._log("🔍 Mendeteksi tipe task: {}".format(task_type.upper()))
        self._log("🤖 Membangun team: {}".format(
            ", ".join(a.name for a in agents.values())))

        # ── Step 1: Orchestrator pecah task ──────────────────────────────────
        self._log("\n📋 [Orchestrator] Menganalisa task...")
        orch_prompt = (
            "Task dari user:\n\n{}\n\n"
            "Tipe task yang terdeteksi: {}\n\n"
            "Analisa task ini dan buat rencana singkat pengerjaan. "
            "Apa yang perlu dijawab? Aspek apa yang paling penting?"
        ).format(task, task_type)

        orch_resp = agents["orchestrator"].think(
            orch_prompt, max_tokens=512
        )
        self.memory.store(session_id, "Orchestrator", "orchestrator",
                          orch_resp.content, model=agents["orchestrator"].last_model_used)
        self._log("   Model: {}".format(agents["orchestrator"].last_model_used))

        # ── Step 2: Primary agent kerjakan task ──────────────────────────────
        self._log("\n⚡ [{}] Mengerjakan task...".format(agents["primary"].name))
        primary_resp = agents["primary"].think(
            task,
            context=orch_resp.content,
            max_tokens=max_tokens,
        )
        self.memory.store(session_id, agents["primary"].name, task_type,
                          primary_resp.content, model=agents["primary"].last_model_used)
        self._log("   Model: {}".format(agents["primary"].last_model_used))

        discussion_log = []

        # ── Step 3: Secondary agent (jika ada) — diskusi ─────────────────────
        if "secondary" in agents:
            self._log("\n💬 [{}] Memberikan perspektif lain...".format(
                agents["secondary"].name))
            secondary_resp = agents["secondary"].think(
                task,
                context=primary_resp.content,
                max_tokens=max_tokens // 2,
            )
            self.memory.store(session_id, agents["secondary"].name,
                              agents["secondary"].task_type,
                              secondary_resp.content,
                              model=agents["secondary"].last_model_used)
            self._log("   Model: {}".format(agents["secondary"].last_model_used))

            # Cek apakah ada perbedaan pendapat
            discussion_log.append({
                "agent":   agents["secondary"].name,
                "content": secondary_resp.content,
                "model":   agents["secondary"].last_model_used,
            })

            # Primary respond ke secondary
            self._log("\n🔄 [{}] Merespons diskusi...".format(
                agents["primary"].name))
            discuss_resp = agents["primary"].discuss(
                task, secondary_resp.content, max_tokens=512
            )
            self.memory.store(session_id, agents["primary"].name,
                              "discuss", discuss_resp.content,
                              model=agents["primary"].last_model_used)
            discussion_log.append({
                "agent":   agents["primary"].name + " (diskusi)",
                "content": discuss_resp.content,
                "model":   agents["primary"].last_model_used,
            })

            # Gabungkan untuk critic
            combined = (
                "=== JAWABAN UTAMA ===\n{}\n\n"
                "=== PERSPEKTIF TAMBAHAN ===\n{}\n\n"
                "=== DISKUSI ===\n{}"
            ).format(primary_resp.content,
                     secondary_resp.content,
                     discuss_resp.content)
        else:
            combined = primary_resp.content

        # ── Step 4: Critic review ─────────────────────────────────────────────
        self._log("\n🔎 [Critic] Me-review hasil...")
        critic_prompt = (
            "Review hasil berikut untuk task: '{}'\n\n"
            "{}\n\n"
            "Berikan: (1) poin kuat, (2) kelemahan jika ada, "
            "(3) saran perbaikan singkat. Jika sudah bagus, cukup konfirmasi."
        ).format(task[:200], combined[:2000])

        critic_resp = agents["critic"].think(
            critic_prompt, max_tokens=512
        )
        self.memory.store(session_id, "Critic", "critic",
                          critic_resp.content, model=agents["critic"].last_model_used)
        self._log("   Model: {}".format(agents["critic"].last_model_used))

        # ── Step 5: Orchestrator finalisasi ──────────────────────────────────
        self._log("\n✅ [Orchestrator] Membuat output final...")
        final_prompt = (
            "Task awal: {}\n\n"
            "=== HASIL KERJA ===\n{}\n\n"
            "=== REVIEW CRITIC ===\n{}\n\n"
            "Buat output final yang komprehensif, jelas, dan langsung bermanfaat "
            "untuk user. Integrasikan semua insight terbaik."
        ).format(task[:300], combined[:2000], critic_resp.content[:500])

        final_resp = agents["orchestrator"].think(
            final_prompt,
            stream_cb=self.stream_cb,
            max_tokens=max_tokens,
        )
        self.memory.store(session_id, "Orchestrator", "final",
                          final_resp.content, msg_type="final",
                          model=agents["orchestrator"].last_model_used)

        self.memory.finish_session(session_id, final_resp.content)

        agents_used = {
            name: {"model": a.last_model_used, "role": a.role}
            for name, a in agents.items()
        }

        self._log("\n✨ Selesai!")

        return {
            "result":      final_resp.content,
            "session_id":  session_id,
            "task_type":   task_type,
            "agents_used": agents_used,
            "discussion":  discussion_log,
            "critic":      critic_resp.content,
        }

    def quick(self, task: str, max_tokens: int = 1024) -> str:
        """
        Mode cepat — single agent tanpa diskusi.
        Cocok untuk task simpel.
        """
        from .roles import auto_select_agent
        agent = auto_select_agent(task, self.keys)
        self._log("⚡ Quick mode: {}".format(agent.task_type.upper()))
        resp = agent.think(task, stream_cb=self.stream_cb, max_tokens=max_tokens)
        self._log("   Model: {}".format(agent.last_model_used))
        return resp.content
