"""Chat history with rolling summarisation.

Two concerns kept separate: the full display history (UI) vs. the bounded context
actually sent to the LLM. Every 10 turns the oldest batch is compressed into a
running summary so prompts stay small no matter how long the conversation runs.
"""
from __future__ import annotations


class ChatHistory:
    def __init__(self, llm_client) -> None:
        self.turns: list[dict] = []
        self.summary: str = ""
        self.unsummarised_start: int = 0
        self.llm = llm_client  # lightweight router model

    def add_turn(self, role: str, content: str) -> None:
        self.turns.append({"role": role, "content": content})
        if len(self.turns) % 10 == 0:
            self._summarise()

    def _summarise(self) -> None:
        batch = self.turns[self.unsummarised_start:self.unsummarised_start + 10]
        text = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in batch)
        prompt = (
            "Summarise this conversation in 2-4 sentences, capturing key topics and "
            "conclusions:\n\n" + text
        )
        try:
            new_summary = self.llm.invoke([{"role": "user", "content": prompt}]).content.strip()
        except Exception:
            return  # summarisation is best-effort; never break the turn
        self.summary = f"{self.summary} Later: {new_summary}" if self.summary else new_summary
        self.unsummarised_start += 10

    def get_context_messages(self) -> list[dict]:
        messages: list[dict] = []
        if self.summary:
            messages.append({
                "role": "system",
                "content": f"Summary of earlier conversation: {self.summary}",
            })
        messages.extend(self.turns[self.unsummarised_start:])
        return messages
