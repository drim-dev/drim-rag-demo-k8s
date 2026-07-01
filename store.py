"""Qdrant store: one collection with named vectors {dense, sparse} for hybrid search.

Knowledge map: open http://localhost:6333/dashboard -> Collections -> scheduler_memory
-> Visualize, color by payload field `pile` to see the four piles.
"""

import uuid

from qdrant_client import QdrantClient, models

from config import COLLECTION, DENSE_DIM, QDRANT_URL

_NAMESPACE = uuid.UUID("6b6a8c1e-0000-4000-8000-5c4ed1110000")


def make_point_id(pile: str, path: str, index: int) -> str:
    """Stable id so re-indexing upserts the same point (idempotent, no duplicates)."""
    return str(uuid.uuid5(_NAMESPACE, f"{pile}:{path}:{index}"))


def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client: QdrantClient) -> None:
    if client.collection_exists(COLLECTION):
        return
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={"dense": models.VectorParams(size=DENSE_DIM, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    # Payload index on `pile` makes filtering (and the Visualize coloring) efficient.
    client.create_payload_index(COLLECTION, "pile", models.PayloadSchemaType.KEYWORD)
    client.create_payload_index(COLLECTION, "path", models.PayloadSchemaType.KEYWORD)


def upsert_points(client: QdrantClient, points: list[dict]) -> None:
    """Each point dict: {id, dense: list[float], sparse: (indices, values), payload: dict}."""
    structs = []
    for p in points:
        indices, values = p["sparse"]
        structs.append(models.PointStruct(
            id=p["id"],
            vector={
                "dense": p["dense"],
                "sparse": models.SparseVector(indices=indices, values=values),
            },
            payload=p["payload"],
        ))
    client.upsert(collection_name=COLLECTION, points=structs)
