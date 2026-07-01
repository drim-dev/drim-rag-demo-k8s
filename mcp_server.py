"""MCP server exposing kube-scheduler institutional memory to a coding agent.

This is the lecture climax: RAG becomes a tool the agent calls mid-task (callback to
the MCP lecture). Register in Claude Code:

    claude mcp add --transport stdio scheduler-memory -- uv run python mcp_server.py

Then in Claude Code `/mcp` should list `search_org_memory`. The killer demo: ask the
agent to implement cross-node preemption — without this tool it reinvents the rejected
"guarantee the freed node" approach; with it, it retrieves the rationale and avoids it.
"""

from mcp.server.fastmcp import FastMCP

from retrieval import RetrievedChunk, Retriever

mcp = FastMCP("scheduler-memory")
_retriever = Retriever()

MAX_CHARS = 2000  # per chunk, to keep tool output within the agent's context budget


def _citation(c: RetrievedChunk) -> str:
    p = c.payload
    if c.pile == "code":
        return f"code · {p.get('symbol_type', '')} {p.get('symbol_name', '')} · {c.path}"
    if c.pile == "kep":
        return f"kep · {p.get('kep_number', '')} · {p.get('section', '')} · {c.path}"
    if c.pile == "issue":
        return f"issue · #{p.get('number', '')} ({p.get('kind', '')}) {p.get('title', '')} · {p.get('message', '')}"
    return f"docs · {p.get('title', '')} · {p.get('section', '')} · {c.path}"


@mcp.tool()
def search_org_memory(query: str, pile: str | None = None, top_k: int = 6) -> str:
    """Search kube-scheduler institutional memory: source code (pkg/scheduler), KEPs,
    issue/PR discussion threads, and component docs.

    Call this BEFORE proposing or implementing scheduler changes — it surfaces the
    documented rationale and, crucially, approaches that were considered and REJECTED,
    so you don't reinvent a design the maintainers already turned down.

    Args:
        query: natural-language question or exact identifier (e.g. "NominatedNodeName").
        pile: optionally restrict to one of "code" | "kep" | "issue" | "docs".
        top_k: number of results (default 6).
    """
    results = _retriever.search(query, top_k=top_k, mode="hybrid", pile=pile, rerank=True)
    if not results:
        return "No results in scheduler institutional memory for this query."

    blocks = [f"{len(results)} results for: {query!r}\n"]
    for i, c in enumerate(results, 1):
        text = c.text.strip()
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + " …[truncated]"
        blocks.append(f"--- [{i}] {_citation(c)} (score={c.score:.3f})\n{text}")
    return "\n\n".join(blocks)


if __name__ == "__main__":
    mcp.run(transport="stdio")
