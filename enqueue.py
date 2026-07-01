"""Manual publisher to the live-update stream (demo without a public webhook URL).

    uv run python enqueue.py 124978          # re-index issue/PR #124978
"""

import argparse

import redis

from config import REDIS_URL, STREAM


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ref", help="issue/PR number")
    parser.add_argument("--type", default="issue")
    args = parser.parse_args()

    r = redis.from_url(REDIS_URL, decode_responses=True)
    msg_id = r.xadd(STREAM, {"type": args.type, "ref": str(args.ref)})
    print(f"queued {args.type} {args.ref} as {msg_id} on '{STREAM}'")


if __name__ == "__main__":
    main()
