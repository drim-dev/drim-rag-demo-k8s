"""Live-update worker: Redis Streams consumer-group → index into Qdrant.

Reads index requests (XREADGROUP), re-indexes the referenced item, then XACKs.
On error the message stays pending (not acked) — durability you can show in the demo
via `XPENDING scheduler-memory:index indexers`.

    uv run python worker.py
"""

import os

import redis

import ingest
from config import GROUP, REDIS_URL, STREAM
from store import ensure_collection, get_client

CONSUMER = os.getenv("CONSUMER_NAME", "worker-1")


def _ensure_group(r: redis.Redis) -> None:
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def _handle(client, fields: dict) -> None:
    kind = fields.get("type")
    ref = fields.get("ref")
    if kind == "issue":
        n = ingest.index_issue_number(client, int(ref))
        print(f"  indexed issue #{ref}: {n} chunks")
    else:
        print(f"  ignoring unknown type: {kind!r}")


def main() -> None:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    _ensure_group(r)
    client = get_client()
    ensure_collection(client)
    print(f"worker '{CONSUMER}' listening on stream '{STREAM}' (group '{GROUP}')")

    while True:
        resp = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=1, block=5000)
        if not resp:
            continue
        for _stream, messages in resp:
            for msg_id, fields in messages:
                try:
                    _handle(client, fields)
                    r.xack(STREAM, GROUP, msg_id)
                except Exception as e:  # leave pending for retry / inspection
                    print(f"  error on {msg_id}: {e} (left pending)")


if __name__ == "__main__":
    main()
