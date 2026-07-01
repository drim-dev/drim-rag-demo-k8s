"""GitHub webhook receiver → publishes index requests to the Redis Stream.

    uv run uvicorn webhook:app --port 8000

Point a GitHub webhook (issues / issue_comment / pull_request events) at
http://<host>:8000/github/webhook. Without a public URL, use a tunnel or enqueue.py.
Set GITHUB_WEBHOOK_SECRET to enforce HMAC signature verification.
"""

import hashlib
import hmac
import json

import redis
from fastapi import FastAPI, Header, HTTPException, Request

from config import GITHUB_WEBHOOK_SECRET, REDIS_URL, STREAM

app = FastAPI()
_redis = redis.from_url(REDIS_URL, decode_responses=True)


def _verify(body: bytes, signature: str | None) -> bool:
    if not GITHUB_WEBHOOK_SECRET:
        return True  # verification disabled
    if not signature:
        return False
    digest = hmac.new(GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature)


@app.post("/github/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    body = await request.body()
    if not _verify(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="invalid signature")

    payload = json.loads(body)
    item = payload.get("issue") or payload.get("pull_request")
    if item and "number" in item:
        msg_id = _redis.xadd(STREAM, {"type": "issue", "ref": str(item["number"])})
        return {"queued": item["number"], "event": x_github_event, "msg_id": msg_id}
    return {"ignored": x_github_event}
