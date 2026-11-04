"""Agent-callable website capabilities backed by web_bridge services."""
from .browser import BROWSER_TOOLS
from .page import PAGE_TOOLS
from .transfer import TRANSFER_TOOLS

WEBSITE_TOOLS = [*BROWSER_TOOLS, *TRANSFER_TOOLS, *PAGE_TOOLS]

__all__ = ["WEBSITE_TOOLS", "BROWSER_TOOLS", "PAGE_TOOLS", "TRANSFER_TOOLS"]
