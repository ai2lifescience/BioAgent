"""OpenAI-hosted tools, when the configured model/runtime supports them."""

# Kept as an explicit extension point. Pipeline2Agent currently uses local
# FunctionTools for biological APIs and does not register hosted tools.
HOSTED_TOOLS = []

__all__ = ["HOSTED_TOOLS"]
