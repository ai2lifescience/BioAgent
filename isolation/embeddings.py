"""Bounded embedding RPC; the configured model client stays on the server."""
TOOLS = frozenset({'evidence_index', 'evidence_retrieve'})


def calculate(payload, tool):
    from models.config import DEFAULT_EMBEDDING_MODEL
    from tools.infrastructure.tool_support.embeddings import embed_texts
    if tool not in TOOLS or not isinstance(payload, dict) or set(payload) - {'texts', 'model'}:
        raise ValueError('This tool has no embedding capability.')
    texts = payload.get('texts')
    if (not isinstance(texts, list) or not 1 <= len(texts) <= 64
            or any(not isinstance(text, str) or len(text) > 12000 for text in texts)
            or sum(len(text) for text in texts) > 512000):
        raise ValueError('Embedding batch exceeds its limit.')
    if payload.get('model', DEFAULT_EMBEDDING_MODEL) != DEFAULT_EMBEDDING_MODEL:
        raise ValueError('The index requires an embedding model not configured on this server.')
    return {'vectors': embed_texts(texts, model=DEFAULT_EMBEDDING_MODEL)}


def install(module, reader, writer):
    import json
    from .protocol import MAX_WIRE
    from models.config import DEFAULT_EMBEDDING_MODEL
    def embed(texts, model=DEFAULT_EMBEDDING_MODEL):
        writer.write(json.dumps({'embedding_request': {'texts': list(texts), 'model': model}}).encode() + b'\n')
        writer.flush()
        line = reader.readline(MAX_WIRE + 1)
        if len(line) > MAX_WIRE:
            raise ValueError('Embedding response exceeds its limit.')
        reply = json.loads(line)
        if 'error' in reply:
            raise ValueError(reply['error'])
        return reply['vectors']
    module.embed_texts = embed
