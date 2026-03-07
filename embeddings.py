import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)

# Embedding model: "titan" (default, works without Nova) or "nova"
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "titan").lower().strip()

# Titan: amazon.titan-embed-text-v2:0 (enable in Bedrock Model access)
TITAN_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
# Nova: amazon.nova-2-multimodal-embeddings-v1:0 (enable in Bedrock Model access)
NOVA_EMBED_MODEL = "amazon.nova-2-multimodal-embeddings-v1:0"

EMBED_DIMENSION = 1024


def _get_client():
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.client("bedrock-runtime", region_name=region)


def _embed_titan(text: str) -> list[float] | None:
    """Titan Text Embeddings V2. Request/response differ from Nova."""
    client = _get_client()
    body = {"inputText": text[:50_000], "dimensions": EMBED_DIMENSION}
    response = client.invoke_model(
        modelId=TITAN_EMBED_MODEL,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    out = json.loads(response["body"].read())
    emb = out.get("embedding")
    return emb if isinstance(emb, list) else None


def _embed_nova(text: str) -> list[float] | None:
    """Nova Multimodal Embedding."""
    client = _get_client()
    body = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "TEXT_RETRIEVAL",
            "embeddingDimension": EMBED_DIMENSION,
            "text": {"truncationMode": "END", "value": text[:8000]},
        },
    }
    response = client.invoke_model(
        modelId=NOVA_EMBED_MODEL,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    out = json.loads(response["body"].read())
    emb_list = out.get("embeddings") or []
    if not emb_list:
        return None
    emb = emb_list[0].get("embedding")
    return emb if isinstance(emb, list) else None


def embed_text(text: str) -> list[float] | None:
    """Generate embedding (Titan or Nova per EMBEDDING_MODEL). Returns None on failure."""
    if not (text or text.strip()):
        return None
    try:
        if EMBEDDING_MODEL == "nova":
            return _embed_nova(text)
        return _embed_titan(text)
    except Exception as e:
        logger.exception("Bedrock embedding failed: %s", e)
        return None


def embed_text_with_error(text: str) -> tuple[list[float] | None, str | None]:
    """Same as embed_text but returns (embedding, error_message). Error is None on success."""
    if not (text or text.strip()):
        return None, "Empty text"
    try:
        if EMBEDDING_MODEL == "nova":
            emb = _embed_nova(text)
        else:
            emb = _embed_titan(text)
        if not emb:
            return None, "No embedding in response"
        return emb, None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        return None, err
