# Проектное решение: scheduler-org-memory (демо к лекции RAG)

Демо к лекции 10 «RAG» курса AI Superpower for Developers (поток ai-course-3, 2GIS).
Спина лекции: **RAG — институциональная память инженерной организации, до которой дотягивается агент; RAG меняет выход разработки.**
Структура лекции: `lectures/rag-lecture-structure.md`.

**Расположение.** Проект живёт внутри этого репозитория (`demos/scheduler-org-memory/`); позже выносится в отдельный репозиторий — поэтому самодостаточный, без зависимостей от Aspire/backend/frontend.

**Происхождение.** Не эволюция одного app на месте, а новый проект, переиспользующий **паттерны** из `courses/ai-for-developers/drim-rag-demo`: из **app-2** — Qdrant + гибрид (BM25+вектор) + RRF + реранк + фильтры (`app-2-python-docs-assistant/retrieval.py`); из **app-3** — чанкинг (tree-sitter Go, markdown по заголовкам), инкрементальная индексация, eval-харнес, трекинг стоимости/задержек, ингест-скрипты.

---

## Что демо должно показать (привязка к актам лекции)

1. **Четыре кучи памяти** kube-scheduler: код, KEP, треды issues/PR, доки. Сердце — две «кучи почему» (KEP + PR).
2. **Карта знаний визуально** — Qdrant Dashboard (вкладка Visualize): 2D-проекция векторов, раскраска точек по `pile` → видно четыре кучи как карту орг-памяти. Сильный визуальный ход открытия лекции.
3. **Наивный вектор мажет по идентификаторам → гибрид (BM25+вектор+RRF)+реранк.** Бит «до/после».
4. **Метаданные/фильтры** — скоуп по куче/пути/`sig-scheduling`/свежести.
5. **MCP-сервер** `search_org_memory` → Claude Code достаёт орг-знание прямо в задаче (кульминация, отсылка к лекции MCP).
6. **Killer-демо вытеснения (с/без RAG):** без RAG агент берёт отвергнутый в KEP/PR подход; с RAG обходит.
7. **Очередь живого обновления (как в проде):** новый коммент в issue/PR → вебхук → очередь → воркер индексирует → точка появляется на карте Qdrant → агент сразу её достаёт. Показывает инкрементальную индексацию вживую (задел под дрейф из лекции A: «устаревший индекс хуже отсутствующего»).
8. **Retrieval-eval** — вопрос → ожидаемые источники → доля попаданий (precision@k/recall@k/MRR).

---

## Решения (зафиксированы)

1. **Реранкер — локальный** cross-encoder `BAAI/bge-reranker-base` (`sentence-transformers`). Cohere — опция флагом.
2. **Очередь — Redis Streams** (consumer-group, durability). Триггеры: вебхук (мгновенно), manual, cron.
3. **Killer-сценарий — cross-node preemption / «гарантировать поду освобождённую ноду».** Это интуитивный, но **отвергнутый** подход с явным разделом «Decision/Alternatives Considered». Без RAG агент реализует «гарантию освобождённой ноды» и/или кластерный поиск жертв; с RAG достаёт отказ и обходит.
   - **Что отвергли и почему (рационал для ретривала):** preemption НЕ гарантирует поду освобождённую ноду — это лишь `status.nominatedNodeName` как подсказка (гонки, переезд на другую ноду); cross-node preemption отвергнут как «prohibitively expensive in large clusters».
   - **Целевой источник:** `kubernetes/design-proposals-archive` → `scheduling/pod-preemption.md` (разделы «Supporting Cross Node Preemption?», «Notes», «Alternatives Considered»). Подтверждающий: `keps/sig-scheduling/1923-prefer-nominated-node/README.md` («предпочитаем, но не гарантируем»). Запасной бит из того же файла: «preempt by QoS first» (тоже отвергнут).
   - **⚠️ Добавить в корпус:** `pod-preemption.md` живёт в **`kubernetes/design-proposals-archive`** — это пятый источник вне четырёх куч. В Ф5 куча `kep` дополняется загрузкой канонических design-proposals по теме (минимум `scheduling/pod-preemption.md`).

---

## Архитектура

```
Источники (4 кучи)                          Живое обновление
  download_*.py (bulk-ингест)               webhook.py (FastAPI) ← GitHub webhook
        │                                          │ enqueue
        ▼                                          ▼
  index.py ──enqueue──────────────────►  Redis (очередь) ──► worker.py (RQ)
                                                                  │ chunk → embed → upsert
                                                                  ▼
   dense: Ollama nomic-embed-text (768d)            ┌──────────────────────────┐
   sparse: fastembed BM25                ──────────►│  Qdrant  collection       │
   payload: {pile, path, sig, updated_at,...}       │  scheduler_memory         │
                                                     │  (named vectors: dense+sparse) │
                                                     └──────────────────────────┘
                                                                  │  Dashboard :6333/dashboard
   retrieval.py (общий модуль):                                   │  → Visualize = карта знаний
     Qdrant hybrid (dense+sparse, RRF server-side)                ▼
     → cross-encoder rerank → top-k                  фильтры по payload (pile/path/freshness)
        ┌──────────────┴───────────────┐
        ▼                              ▼
   mcp_server.py (FastMCP)        app.py (Streamlit)
   tool search_org_memory          чат + индексация + eval + тумблер «с/без RAG» + ссылка на карту
        │
        ▼
   Claude Code  ──→  killer-демо вытеснения
```

**Структурный ключ:** общий `retrieval.py`, который используют и Streamlit, и MCP-сервер, и (для самопроверки) eval. Один путь ретривала.

---

## Стек

- **Векторное хранилище: Qdrant** (Docker, порт 6333; Dashboard `http://localhost:6333/dashboard`).
  - **Гибрид нативно:** именованные векторы dense + sparse, серверный fusion (RRF). dense — Ollama `nomic-embed-text` (768d, локально), sparse — fastembed `Qdrant/bm25`.
  - **Карта знаний:** вкладка Visualize, раскраска по payload `pile`.
- **Обвязка ретривала/индексации: прямой `qdrant-client`** (не LlamaIndex) — прозрачнее для лекции: видно dense+sparse, fusion, payload. Чанкинг портируем вручную из app-3.
- **Реранк:** локальный cross-encoder `BAAI/bge-reranker-base` (`sentence-transformers`). [решено]
- **Очередь: Redis Streams** (`worker.py` — consumer-group, durability, повторная обработка); `webhook.py` на FastAPI публикует события в stream. [решено]
- **Генерация:** Anthropic (в Streamlit); в MCP-сценарии генерирует сам Claude Code.
- **MCP:** `fastmcp`. **GitHub API:** `requests` + `GITHUB_TOKEN`.

Зависимости (`pyproject.toml`, uv): `qdrant-client[fastembed]` (sparse BM25 + dense), `sentence-transformers` (реранк), `mcp` (MCP-сервер; FastMCP бандлится как `mcp.server.fastmcp`), `redis` (Streams), `fastapi`+`uvicorn` (вебхук), `streamlit`, `anthropic`, `tree-sitter`+`tree-sitter-go`, `requests`, `pandas`, `python-dotenv`. Dense-эмбеддинги — Ollama `nomic-embed-text` через REST.

---

## Четыре кучи: ингест

| Куча | Источник | Скрипт | Чанкинг | Payload |
|---|---|---|---|---|
| Код | `pkg/scheduler/**` из `kubernetes/kubernetes` | `download_code.py` | tree-sitter Go по символам (порт из app-3) | `pile=code, path, package, symbol_name, symbol_type` |
| KEP | `keps/sig-scheduling/**/README.md` из `kubernetes/enhancements` | `download_keps.py` | markdown по заголовкам | `pile=kep, kep_number, title, section, status` |
| Обсуждения | issues+PR с `label:sig/scheduling`, **тело + комментарии**, GitHub API | `download_issues.py` | по сообщению (тело + каждый коммент = чанк) | `pile=issue, number, kind, title, updated_at` |
| Доки | страницы планировщика из `kubernetes/website` | `download_docs.py` | markdown по заголовкам | `pile=docs, path, page_title, section` |

«Куча почему» №2 (issues+PR) — самый объёмный новый кусок: рационал и отказы живут в **комментариях** → тянем `/comments`, не только тело. Свежесть (`updated_at`) с GitHub API кормит и фильтр свежести, и демо живого обновления.

---

## Очередь живого обновления (production-like, Redis Streams)

- **`webhook.py` (FastAPI):** endpoint `/github/webhook` принимает события issue/PR-comment по `sig/scheduling` и публикует в Redis Stream (`XADD scheduler-memory:index ...`). Для демо без публичного URL — туннель или ручной вызов/скрипт.
- **`worker.py`:** consumer-group читает stream (`XREADGROUP`), на каждое событие: fetch → chunk → embed (dense+sparse) → upsert в Qdrant, затем `XACK`. Идемпотентно по id чанка (uuid5 от pile+path+index), повторы не плодят дубли; необработанные остаются в pending (durability).
- **`enqueue.py`:** ручной публикатор в тот же stream (`enqueue.py <issue|pr ref>`).
- **Триггеры:** вебхук (мгновенно), manual, cron (периодический re-scan). Зеркалит production-раздел тела урока (webhook/cron/manual, Data Freshness SLA). Consumer-group/pending/XACK — повод показать «как в проде».
- **Демо вживую:** добавить коммент в отслеживаемый issue → точка появляется на карте Qdrant → `search_org_memory` уже находит. Замыкает на дрейф из лекции A.

---

## Build (по фазам)

- **Ф0 — каркас:** `demos/scheduler-org-memory/` + `docker-compose.yml` (Qdrant + Redis + Ollama), `pyproject.toml`, `config.py`, `.env.example`, `README.md`.
- **Ф1 — кучи и индексация:** 4 download-скрипта; `index.py` (чанкинг по типу, payload, инкрементально по хешу), запись в Qdrant. Проверка: карта Qdrant показывает четыре кучи цветом.
- **Ф2 — гибрид+реранк+`retrieval.py`:** Qdrant hybrid (dense+sparse, RRF) + cross-encoder реранк + фильтры по payload. Проверка: бит «наивный мажет по идентификатору → гибрид находит».
- **Ф3 — MCP-сервер:** `mcp_server.py` (FastMCP) `search_org_memory(query, pile?, top_k)` → ранжированные чанки с цитатами; регистрация в Claude Code. Проверка: агент вызывает инструмент.
- **Ф4 — очередь:** `worker.py` (RQ) + `webhook.py` (FastAPI) + `enqueue.py`. Проверка: новый коммент → карта обновилась → агент достаёт.
- **Ф5 — killer-сценарий + retrieval-eval:** реальный отвергнутый подход; датасет вопрос→ожидаемые источники; метрика hit-rate/precision@k/recall@k/MRR; тумблер «с/без RAG». Проверка: контраст «с/без RAG» воспроизводится.

---

## Инструкции запуска (целевой поток — после реализации)

Предусловия: `uv`, Python 3.11+, Docker, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, ~8 ГБ под Ollama-модель и данные.

```bash
cd demos/scheduler-org-memory

# 1. Инфраструктура: Qdrant + Redis + Ollama (+ автозагрузка nomic-embed-text)
docker compose up -d
#    карта знаний: http://localhost:6333/dashboard  → Collections → Visualize

# 2. Зависимости и окружение
uv sync
cp .env.example .env          # ANTHROPIC_API_KEY, GITHUB_TOKEN

# 3. Наполнить данными — четыре кучи
uv run python scripts/download_code.py      # pkg/scheduler/**
uv run python scripts/download_keps.py      # keps/sig-scheduling/**
uv run python scripts/download_issues.py    # label:sig/scheduling, тело + треды
uv run python scripts/download_docs.py       # страницы планировщика

# 4. Индексация (инкрементально; --force для полной)
uv run python index.py --source all
#    открыть карту в Qdrant Dashboard, раскрасить по pile → четыре кучи

# 5. Живое обновление (как в проде, Redis Streams)
uv run python worker.py &                           # consumer-group воркер
uv run uvicorn webhook:app --port 8000 &            # приёмник вебхуков → XADD
#    демо: uv run python enqueue.py <issue|pr ref>  → точка появляется на карте

# 6a. UI с тумблером «с/без RAG» и страницей eval
uv run streamlit run app.py

# 6b. Кульминация — RAG как инструмент агента
claude mcp add --transport stdio scheduler-memory -- uv run python mcp_server.py
#    в Claude Code: /mcp → проверить search_org_memory
#    killer-задача про вытеснение — сравнить ответ с инструментом и без

# 7. Retrieval-eval (hit-rate по ожидаемым источникам)
uv run python evaluate.py --mode retrieval
```

**Статус реализации:** Ф0–Ф5 реализованы — все фазы.
- Ф0–Ф1: каркас + ингест четырёх куч + индексация в Qdrant.
- Ф2: гибридный ретривал `retrieval.py` (dense+sparse RRF) + локальный реранк.
- Ф3: MCP-сервер `mcp_server.py` (`search_org_memory`).
- Ф4: очередь Redis Streams — `ingest.py`/`worker.py`/`webhook.py`/`enqueue.py`.
- Ф5: пятый источник design-proposals (`download_designs.py`) + retrieval-eval (`evaluate.py`, `eval_dataset.json`) + killer-сценарий (`KILLER_DEMO.md`).

Синтаксис всех модулей проверен; end-to-end прогон и наполнение данными — за Димой (нужны Docker/Ollama/сеть/зависимости).
