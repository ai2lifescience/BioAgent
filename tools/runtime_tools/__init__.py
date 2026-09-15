"""SDK local/runtime tools such as ShellTool or ComputerTool."""

# The pipeline runner is intentionally a guarded FunctionTool. Generic local
# execution tools remain disabled until a workflow requires their semantics.
RUNTIME_TOOLS = []

__all__ = ["RUNTIME_TOOLS"]
