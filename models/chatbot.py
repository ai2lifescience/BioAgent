"""Interactive chatbot backed by the BioAgent Agents SDK runtime."""

from __future__ import annotations

from typing import Callable

from harness.runtime import run_bioagent
from .config import DEFAULT_AGENT_MODEL_KEY


class ModelChatbot:
    def __init__(self, model_key: str = DEFAULT_AGENT_MODEL_KEY) -> None:
        self.model_key = model_key
        self.session_id: str | None = None

    def ask(self, user_text: str, log_fn: Callable[[str], None] | None = None) -> str:
        result = run_bioagent(user_text, session_id=self.session_id, model_key=self.model_key, log_fn=log_fn)
        self.session_id = str(result["session_id"])
        return str(result["answer"])

    def reset(self) -> None:
        self.session_id = None


def chat_loop() -> int:
    bot = ModelChatbot()
    print(f"Chatting with {bot.model_key}. Type /reset to clear history or /exit to quit.")
    while True:
        try:
            user_text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user_text:
            continue
        if user_text in {"/exit", "/quit"}:
            return 0
        if user_text == "/reset":
            bot.reset()
            print("History reset.")
            continue
        try:
            print(f"\nAssistant: {bot.ask(user_text)}")
        except Exception as exc:
            print(f"Model error: {exc}")


if __name__ == "__main__":
    raise SystemExit(chat_loop())
