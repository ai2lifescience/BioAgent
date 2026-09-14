"""BioAgent's single OpenAI Agents SDK runtime.

The public functions are loaded lazily so deterministic workflows can import
``harness.workflow_context`` without importing the registry and creating a
package initialization cycle.
"""

__all__ = ["async_run_bioagent", "run_bioagent"]


def __getattr__(name: str):
    if name in __all__:
        from .runtime import async_run_bioagent, run_bioagent
        return {"async_run_bioagent": async_run_bioagent, "run_bioagent": run_bioagent}[name]
    raise AttributeError(name)
