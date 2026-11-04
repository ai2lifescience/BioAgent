"""Observe the connected host tab without an agent SDK dependency."""
from ..bridge import get_bridge


async def observe_page(binding, run_id: str = "") -> dict:
    if not binding:
        raise ValueError('Open the assistant on the website to inspect its current tab. Backend push/pull does not require a tab.')
    return await get_bridge().request(binding, run_id=run_id, method='observePage', arguments={})
