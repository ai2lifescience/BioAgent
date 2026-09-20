"""Pipeline2Agent's single OpenAI Agents SDK runtime.

The public functions are loaded lazily so tool modules can import the runtime
context without creating a package initialization cycle.
"""

__all__ = ["async_run_agent", "run_agent", "async_resume_agent", "resume_agent"]


def __getattr__(name: str):
    if name in __all__:
        from . import runtime
        return getattr(runtime, name)
    raise AttributeError(name)
