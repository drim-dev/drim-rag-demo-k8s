"""Streamlit UI: ask questions against kube-scheduler institutional memory.

Shows how RAG works WITHOUT the agent/MCP path — a human asks, the system retrieves
and answers with citations. The "Использовать RAG" toggle is the lecture's contrast:
with RAG the answer is grounded in retrieved sources and cites them; without RAG the
model answers from its own parametric knowledge, no sources.

    uv run streamlit run app.py
"""

import anthropic
import streamlit as st

import config
from retrieval import RetrievedChunk, Retriever

SYSTEM_RAG = (
    "Ты помогаешь разработчику разобраться в устройстве планировщика Kubernetes "
    "(kube-scheduler). Отвечай СТРОГО по приведённым фрагментам институциональной памяти "
    "(код, KEP, обсуждения, документация) и ссылайся на источники в квадратных скобках: [1], [2]. "
    "Если в фрагментах нет ответа — прямо скажи об этом, не выдумывай. "
    "Отвечай по-русски; точные идентификаторы и цитаты из источников приводи как есть."
)

SYSTEM_NO_RAG = (
    "Ты помогаешь разработчику разобраться в устройстве планировщика Kubernetes "
    "(kube-scheduler). Отвечай из собственных знаний. Источников у тебя нет — "
    "не выдумывай ссылки и цитаты; если не уверен в детали, честно это скажи. "
    "Отвечай по-русски."
)


@st.cache_resource
def get_retriever() -> Retriever:
    return Retriever()


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY (config loaded .env)


def cite(c: RetrievedChunk) -> str:
    p = c.payload
    if c.pile == "code":
        return f"code · {p.get('symbol_type', '')} {p.get('symbol_name', '')} · {c.path}"
    if c.pile == "kep":
        return f"kep · {p.get('section', '')} · {c.path}"
    if c.pile == "issue":
        return f"issue #{p.get('number', '')} · {p.get('title', '')}"
    return f"docs · {p.get('section', p.get('title', ''))} · {c.path}"


def build_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(f"[{i}] {cite(c)}\n{c.text.strip()}" for i, c in enumerate(chunks, 1))


@st.cache_data(show_spinner=False)
def to_english(query: str) -> str:
    """Translate the question to English for retrieval. The corpus is English and the
    reranker/BM25 don't cross languages, so a Russian query scores ~0; the answer itself
    still comes back in the user's language."""
    resp = get_client().messages.create(
        model=config.TRANSLATE_MODEL,
        max_tokens=200,
        system=(
            "Translate the user's kube-scheduler question into an English search query. "
            "Keep code identifiers, API field names, and technical terms unchanged. "
            "Output only the translation — no quotes, no preamble."
        ),
        messages=[{"role": "user", "content": query}],
    )
    return next(b.text for b in resp.content if b.type == "text").strip()


st.set_page_config(page_title="Память kube-scheduler", layout="wide")
st.title("Институциональная память kube-scheduler")
st.caption(
    "Задайте вопрос про планировщик. С RAG ответ строится по источникам со ссылками; "
    "без RAG модель отвечает из своих знаний."
)

with st.sidebar:
    use_rag = st.toggle("Использовать RAG", value=True)
    mode = st.radio(
        "Ретривал", ["hybrid", "dense"], index=0,
        help="hybrid — BM25 + векторы + реранк; dense — чистый вектор",
        disabled=not use_rag,
    )
    pile = st.selectbox("Куча", ["все", "code", "kep", "issue", "docs"], disabled=not use_rag)
    top_k = st.slider("Сколько фрагментов", 3, 12, 6, disabled=not use_rag)

if not config.ANTHROPIC_API_KEY:
    st.warning("ANTHROPIC_API_KEY не задан в .env — поиск работает, но ответ не сгенерируется.")

query = st.text_input(
    "Вопрос",
    placeholder="Почему вытеснение не гарантирует поду освобождённую ноду?",
)

if query:
    chunks: list[RetrievedChunk] = []
    if use_rag:
        pile_arg = None if pile == "все" else pile
        search_query = to_english(query) if config.ANTHROPIC_API_KEY else query
        if search_query.strip().lower() != query.strip().lower():
            st.caption(f"Запрос переведён для поиска (корпус английский): _{search_query}_")
        with st.spinner("Ищу в институциональной памяти…"):
            chunks = get_retriever().search(
                search_query, top_k=top_k, mode=mode, pile=pile_arg, rerank=(mode == "hybrid"),
            )
        with st.expander(f"Найденные фрагменты ({len(chunks)})", expanded=True):
            for i, c in enumerate(chunks, 1):
                st.markdown(f"**[{i}] {cite(c)}** · score={c.score:.3f}")
                st.code(c.text.strip()[:800], language="text")

    grounded = use_rag and bool(chunks)
    if use_rag and not chunks:
        st.warning("Ничего не нашлось — отвечаю без источников.")
    system = SYSTEM_RAG if grounded else SYSTEM_NO_RAG
    user = (
        f"Фрагменты институциональной памяти:\n\n{build_context(chunks)}\n\nВопрос: {query}"
        if grounded else query
    )

    st.subheader("Ответ · с RAG" if grounded else "Ответ · без RAG")
    if not config.ANTHROPIC_API_KEY:
        st.stop()

    def answer():
        with get_client().messages.stream(
            model=config.GEN_MODEL, max_tokens=2048, system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            yield from stream.text_stream

    st.write_stream(answer)
