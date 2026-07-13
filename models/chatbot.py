"""Simple interactive chatbot backed by the shared LLMClient."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.config import DEFAULT_AGENT_MODEL_KEY, DEFAULT_MODELS
from models.llm_client import LLMClient


DEFAULT_SYSTEM_PROMPT = "You are a concise, helpful assistant."


class ModelChatbot:
    """Small in-memory chat session for any configured model key."""

    def __init__(
        self,
        model_key: str = DEFAULT_AGENT_MODEL_KEY,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self.model_key = model_key
        self.client = LLMClient(model_key=model_key)
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

    def ask(
        self,
        text: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        """Send one user message and append the assistant response to history."""
        self.messages.append({"role": "user", "content": text})
        kwargs: dict[str, Any] = {}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        response = self.client.complete(
            messages=self.messages,
            temperature=temperature,
            **kwargs,
        )
        answer = str(response.choices[0].message.content or "")
        self.messages.append({"role": "assistant", "content": answer})
        return answer

    def reset(self, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> None:
        """Clear chat history while keeping the same model."""
        self.messages = [{"role": "system", "content": system_prompt}]


def choose_model_key() -> str:
    """Prompt the user to choose one configured model key."""
    keys = list(DEFAULT_MODELS)
    print("Available models:")
    for index, key in enumerate(keys, start=1):
        label = DEFAULT_MODELS[key].get("label", key)
        print(f"{index}. {key} ({label})")
    print(f"Default: {DEFAULT_AGENT_MODEL_KEY}")

    value = input("Select model number or key: ").strip()
    if not value:
        return DEFAULT_AGENT_MODEL_KEY
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(keys):
            return keys[index - 1]
    if value in DEFAULT_MODELS:
        return value

    available = ", ".join(keys)
    raise ValueError(f"Unknown model selection '{value}'. Available models: {available}")


def chat_loop() -> int:
    """Run an interactive terminal chatbot."""
    model_key = choose_model_key()
    bot = ModelChatbot(model_key=model_key)
    print(f"Chatting with {model_key}. Type /reset to clear history or /exit to quit.")

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
            answer = bot.ask(user_text)
        except Exception as exc:
            print(f"Model error: {exc}")
            continue
        print(f"\nAssistant: {answer}")


if __name__ == "__main__":
    raise SystemExit(chat_loop())
