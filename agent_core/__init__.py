"""Core BioAgent orchestration package."""

__all__ = ["BioAgentOrchestrator"]


def __getattr__(name: str):
    if name == "BioAgentOrchestrator":
        from .orchestrator import BioAgentOrchestrator

        return BioAgentOrchestrator
    raise AttributeError(name)
