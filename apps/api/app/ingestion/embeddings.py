from openai import OpenAI

from app.config import settings


def get_embedding_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = get_embedding_client()

    resp = client.embeddings.create(model=settings.embedding_model, input=texts)

    sorted_data = sorted(resp.data, key=lambda d: d.index)

    return [item.embedding for item in sorted_data]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
