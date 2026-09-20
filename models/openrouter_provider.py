"""Run-scoped Agents SDK model resolution for the OpenRouter backend."""

from __future__ import annotations

from agents import Model, ModelProvider
from openai import AsyncOpenAI

from .local_tools_model import LocalToolsChatCompletionsModel
from .config import resolve_model_id
from .openrouter_transport import create_async_client


class OpenRouterProvider(ModelProvider):
    """Share one lazy client across a run and its nested specialist agents.

    The application must close the provider after the run (including approval
    pauses). An explicitly supplied client remains owned by its caller.
    """

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self._client = client
        self._owns_client = client is None
        self._models: dict[str, Model] = {}
        self._closed = False

    def get_model(self, model_name: str | None) -> Model:
        if self._closed:
            raise RuntimeError("This model provider is closed; create one for the next run.")
        model_id = resolve_model_id(model_name)
        if model_id not in self._models:
            if self._client is None:
                self._client = create_async_client()
            self._models[model_id] = LocalToolsChatCompletionsModel(
                model=model_id, openai_client=self._client,
            )
        return self._models[model_id]

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._models.clear()
        if self._owns_client and self._client is not None:
            await self._client.close()

    async def __aenter__(self) -> OpenRouterProvider:
        if self._closed:
            raise RuntimeError("This model provider is closed; create one for the next run.")
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()
