from typing import List
from jd2interview.utils.config import settings
from openai import OpenAI

_client = None
def _client_once():
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client

def embed_texts(texts: List[str], model: str | None = None) -> List[List[float]]:
    model = model or getattr(settings, "EMBED_MODEL", "text-embedding-3-small")
    client = _client_once()
    # OpenAI Python SDK v1 returns .data with embeddings in order
    resp = client.embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]