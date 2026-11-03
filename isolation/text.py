"""Bounded text scanning with explicit incomplete-scan reporting."""
from .limits import limits


def scan_lines(path, state):
    budget = limits().scan_bytes
    state.update(truncated=False, bytes_scanned=0)
    with path.open('rb') as stream:
        number = 0
        while state['bytes_scanned'] < budget:
            raw = stream.readline(min(65536, budget - state['bytes_scanned']))
            if not raw: return
            number += 1
            state['bytes_scanned'] += len(raw)
            if not raw.endswith(b'\n') and len(raw) == 65536:
                state['truncated'] = True  # An oversized line is scanned in bounded fragments.
            yield number, raw.decode('utf-8', errors='replace')
        state['truncated'] = state['truncated'] or bool(stream.read(1))
