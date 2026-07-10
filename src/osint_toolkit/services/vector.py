"""Optional Qdrant semantic index for local-first RAG."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.storage.sqlite import connect
from osint_toolkit.utils.config import load_config


def get_vector_config() -> dict[str, Any]:
    cfg = load_config()
    vector = ((cfg.get("knowledge") or {}).get("rag") or {}).get("vector") or {}
    return {
        "enabled": bool(vector.get("enabled", False)),
        "provider": str(vector.get("provider") or "qdrant"),
        "url": str(vector.get("url") or "http://127.0.0.1:6333"),
        "collection": str(vector.get("collection") or "osint_knowledge"),
        "embedding_provider": str(vector.get("embedding_provider") or "fastembed"),
        "embedding_model": str(vector.get("embedding_model") or "BAAI/bge-small-zh-v1.5"),
        "chunk_chars": int(vector.get("chunk_chars") or 900),
        "top_k": int(vector.get("top_k") or 8),
    }


def _optional_imports() -> tuple[Any, Any, str]:
    try:
        from fastembed import TextEmbedding
        from qdrant_client import QdrantClient

        return QdrantClient, TextEmbedding, ""
    except Exception as exc:  # noqa: BLE001
        return None, None, str(exc)


def _client(cfg: dict[str, Any]) -> Any:
    qdrant_client, _embedding_cls, err = _optional_imports()
    if qdrant_client is None:
        raise RuntimeError(f"未安装向量依赖: {err}. 请安装 pip install -e .[vector]")
    return qdrant_client(url=cfg["url"])


def _embedding_model(cfg: dict[str, Any]) -> Any:
    _qdrant_client, embedding_cls, err = _optional_imports()
    if embedding_cls is None:
        raise RuntimeError(f"未安装 embedding 依赖: {err}. 请安装 pip install -e .[vector]")
    return embedding_cls(model_name=cfg["embedding_model"])


def _chunk_text(text: str, *, chunk_chars: int) -> list[str]:
    value = " ".join(str(text or "").split())
    if not value:
        return []
    size = max(240, min(int(chunk_chars), 2000))
    overlap = max(40, size // 8)
    chunks: list[str] = []
    start = 0
    while start < len(value):
        chunks.append(value[start : start + size])
        if start + size >= len(value):
            break
        start += size - overlap
    return chunks[:20]


def _item_text(item: IntelItem) -> str:
    parts = [
        item.title,
        item.summary,
        "\n".join(item.key_points or []),
        item.content,
        " ".join(item.topics or []),
        " ".join(str(x) for x in (item.personal.get("entities") or [])),
        " ".join(str(x) for x in (item.personal.get("tags") or [])),
    ]
    return "\n".join(str(part or "") for part in parts if part)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_items(limit: int) -> list[IntelItem]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT data_json FROM intel_items ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 10000)),),
        ).fetchall()
    finally:
        conn.close()
    items: list[IntelItem] = []
    for row in rows:
        try:
            items.append(IntelItem.from_dict(json.loads(row["data_json"] or "{}")))
        except Exception:  # noqa: BLE001
            continue
    return items


def status() -> dict[str, Any]:
    cfg = get_vector_config()
    qdrant_client, embedding_cls, import_error = _optional_imports()
    indexed = 0
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM knowledge_embeddings").fetchone()
        indexed = int(row["c"] or 0) if row else 0
    payload = {
        "enabled": cfg["enabled"],
        "provider": cfg["provider"],
        "url": cfg["url"],
        "collection": cfg["collection"],
        "embedding_provider": cfg["embedding_provider"],
        "embedding_model": cfg["embedding_model"],
        "dependencies_ready": qdrant_client is not None and embedding_cls is not None,
        "import_error": import_error,
        "indexed_chunks": indexed,
        "qdrant_ready": False,
    }
    if not payload["dependencies_ready"]:
        return payload
    try:
        client = _client(cfg)
        client.get_collections()
        payload["qdrant_ready"] = True
    except Exception as exc:  # noqa: BLE001
        payload["qdrant_error"] = str(exc)
    return payload


def _ensure_collection(client: Any, cfg: dict[str, Any], vector_size: int) -> None:
    from qdrant_client.models import Distance, VectorParams

    names = {c.name for c in client.get_collections().collections}
    if cfg["collection"] in names:
        return
    client.create_collection(
        collection_name=cfg["collection"],
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def index(limit: int = 1000, *, force: bool = False) -> dict[str, Any]:
    cfg = get_vector_config()
    if not cfg["enabled"]:
        return {"ready": False, "indexed": 0, "skipped": 0, "message": "knowledge.rag.vector.enabled 未开启"}
    client = _client(cfg)
    embedder = _embedding_model(cfg)
    items = _load_items(limit)
    chunks: list[dict[str, Any]] = []
    for item in items:
        for idx, text in enumerate(_chunk_text(_item_text(item), chunk_chars=cfg["chunk_chars"])):
            content_hash = _hash(text)
            chunk_id = f"{item.id}:{idx}"
            chunks.append({"item": item, "chunk_id": chunk_id, "text": text, "hash": content_hash})
    if not chunks:
        return {"ready": True, "indexed": 0, "skipped": 0, "collection": cfg["collection"]}
    if not force:
        with connect() as conn:
            rows = conn.execute("SELECT content_hash FROM knowledge_embeddings").fetchall()
            known = {str(row["content_hash"]) for row in rows}
        chunks = [chunk for chunk in chunks if chunk["hash"] not in known]
    if not chunks:
        return {"ready": True, "indexed": 0, "skipped": len(items), "collection": cfg["collection"]}
    vectors = list(embedder.embed([chunk["text"] for chunk in chunks]))
    vector_size = len(vectors[0])
    _ensure_collection(client, cfg, vector_size)
    from qdrant_client.models import PointStruct

    points = []
    now = datetime.now(UTC).isoformat()
    for chunk, vector in zip(chunks, vectors, strict=False):
        item = chunk["item"]
        vector_id = hashlib.sha1(f"{chunk['chunk_id']}:{chunk['hash']}".encode()).hexdigest()
        points.append(
            PointStruct(
                id=vector_id,
                vector=list(vector),
                payload={
                    "item_id": item.id,
                    "chunk_id": chunk["chunk_id"],
                    "title": item.title,
                    "url": item.url,
                    "source": item.source,
                    "text": chunk["text"],
                    "content_hash": chunk["hash"],
                },
            )
        )
    client.upsert(collection_name=cfg["collection"], points=points)
    with connect() as conn:
        for chunk, point in zip(chunks, points, strict=False):
            item = chunk["item"]
            conn.execute(
                "INSERT OR REPLACE INTO knowledge_embeddings "
                "(item_id, chunk_id, provider, model, vector_id, content_hash, text, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    chunk["chunk_id"],
                    cfg["provider"],
                    cfg["embedding_model"],
                    point.id,
                    chunk["hash"],
                    chunk["text"],
                    now,
                ),
            )
        conn.commit()
    return {"ready": True, "indexed": len(points), "skipped": 0, "collection": cfg["collection"]}


def search(query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    cfg = get_vector_config()
    if not cfg["enabled"]:
        return []
    client = _client(cfg)
    embedder = _embedding_model(cfg)
    top_k = max(1, min(int(limit or cfg["top_k"]), 50))
    query_vector = list(next(iter(embedder.embed([query]))))
    hits = client.search(collection_name=cfg["collection"], query_vector=query_vector, limit=top_k)
    out: list[dict[str, Any]] = []
    for hit in hits:
        payload = hit.payload or {}
        out.append(
            {
                "item_id": str(payload.get("item_id") or ""),
                "chunk_id": str(payload.get("chunk_id") or ""),
                "title": str(payload.get("title") or ""),
                "url": str(payload.get("url") or ""),
                "source": str(payload.get("source") or ""),
                "text": str(payload.get("text") or ""),
                "score": float(hit.score or 0.0),
                "source_channel": "semantic",
            }
        )
    return out
