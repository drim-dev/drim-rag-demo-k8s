"""Chunking per pile. Heterogeneous sources chunk differently — the lecture's point.

- code  : tree-sitter Go, one chunk per symbol (func / method / type / interface)
- kep   : markdown split by headers
- docs  : markdown split by headers
- issue : one chunk per message (body + each comment)

Each chunker returns a list of dicts: {"text": str, **extra_payload}.
"""

import re

from tree_sitter import Language, Parser
import tree_sitter_go

GO_LANGUAGE = Language(tree_sitter_go.language())

MIN_CHARS = 50


# --- Markdown (KEP + docs) ---

def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].strip()
    return content


def _extract_title(content: str) -> str:
    m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else "Untitled"


def chunk_markdown(content: str) -> list[dict]:
    """Split markdown by headers into (section, text) chunks."""
    title = _extract_title(content)
    body = _strip_frontmatter(content)

    sections: list[tuple[str, str]] = []
    current_header = "Introduction"
    current = ""
    for line in body.split("\n"):
        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            if current.strip():
                sections.append((current_header, current.strip()))
            current_header = m.group(2).strip()
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        sections.append((current_header, current.strip()))

    chunks = []
    for header, text in sections:
        if len(text.strip()) < MIN_CHARS:
            continue
        chunks.append({"text": text, "title": title, "section": header})
    return chunks


# --- Go code ---

_SYMBOL_NODES = (
    "function_declaration",
    "method_declaration",
    "type_declaration",
    "type_spec",
)


def chunk_go(content: str) -> list[dict]:
    """One chunk per top-level Go symbol."""
    parser = Parser(GO_LANGUAGE)
    tree = parser.parse(content.encode())

    pkg_match = re.search(r"^package\s+(\w+)", content, re.MULTILINE)
    package = pkg_match.group(1) if pkg_match else "unknown"

    chunks: list[dict] = []

    def visit(node):
        if node.type in _SYMBOL_NODES:
            text = content[node.start_byte:node.end_byte]
            if len(text.strip()) >= 20:
                symbol_type = "func" if node.type in ("function_declaration", "method_declaration") else "type"
                name_node = node.child_by_field_name("name")
                symbol_name = content[name_node.start_byte:name_node.end_byte] if name_node else ""
                if symbol_type == "type":
                    for child in node.children:
                        if child.type == "interface_type":
                            symbol_type = "interface"
                            break
                chunks.append({
                    "text": text,
                    "package": package,
                    "symbol_name": symbol_name,
                    "symbol_type": symbol_type,
                })
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return chunks


# --- Issue / PR threads ---

def chunk_thread(record: dict) -> list[dict]:
    """Body + each comment as a separate chunk (rationale lives in comments)."""
    chunks: list[dict] = []
    base = {
        "number": record["number"],
        "kind": record["kind"],
        "title": record["title"],
        "updated_at": record.get("updated_at", ""),
    }
    if record.get("body", "").strip():
        chunks.append({**base, "text": f"{record['title']}\n\n{record['body']}",
                       "message": "body", "author": record.get("author", "")})
    for i, c in enumerate(record.get("comments", [])):
        if c.get("body", "").strip():
            chunks.append({**base, "text": c["body"], "message": f"comment-{i}",
                           "author": c.get("author", "")})
    return [c for c in chunks if len(c["text"].strip()) >= MIN_CHARS]
