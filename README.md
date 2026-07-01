# scheduler-org-memory

Демо к лекции 10 «RAG» (курс AI Superpower for Developers). RAG как **институциональная память инженерной организации** на примере **kube-scheduler**: знание о том, *почему* код такой, живёт в KEP и тредах PR — RAG достаёт его и меняет выход разработки.

Проектное решение и фазы: [`DESIGN.md`](DESIGN.md). Структура лекции — в репозитории курса `drim-dev` (`lectures/rag-lecture-structure.md`).

> Статус: **Ф0–Ф5 реализованы** (каркас + ингест четырёх пластов + индексация в Qdrant + гибридный ретривал с реранком + MCP-сервер + очередь живого обновления + killer-демо + retrieval-eval). Синтаксис проверен; end-to-end прогон и наполнение данными — за тобой.

## Четыре пласта памяти

| Пласт | Источник | Скрипт |
|---|---|---|
| `code` | `pkg/scheduler/**` из `kubernetes/kubernetes` | `scripts/download_code.py` |
| `kep` | `keps/sig-scheduling/**` из `kubernetes/enhancements` | `scripts/download_keps.py` |
| `issue` | issues+PR с меткой `sig/scheduling` (тело + комментарии) | `scripts/download_issues.py` |
| `docs` | страницы планировщика из `kubernetes/website` | `scripts/download_docs.py` |

Пласт `issue` — «почему» №2: рационал и отвергнутые подходы живут в комментариях.

## Предусловия

- [uv](https://docs.astral.sh/uv/), Python 3.11+
- Docker (Qdrant + Redis + Ollama)
- `GITHUB_TOKEN` (обязателен для пласта `issue`, желателен для остальных — снимает лимиты)

## Запуск (Ф0–Ф1)

```bash
# 1. Инфраструктура: Qdrant + Redis + Ollama (+ автозагрузка nomic-embed-text)
docker compose up -d
#    дождитесь, пока ollama-pull скачает модель (docker compose logs -f ollama-pull)

# 2. Зависимости и окружение
uv sync
cp .env.example .env        # впишите GITHUB_TOKEN

# 3. Наполнить данными — четыре пласта
uv run python scripts/download_code.py
uv run python scripts/download_keps.py
uv run python scripts/download_issues.py
uv run python scripts/download_docs.py
uv run python scripts/download_designs.py    # design-proposals (killer-демо) → пласт kep

# 4. Индексация (инкрементально; --force для полной; --source code|kep|issue|docs)
uv run python index.py --source all
```

## Ретривал (Ф2): гибрид + реранк

Общий модуль `retrieval.py` — нативный гибрид Qdrant (dense + sparse, серверный RRF) + локальный cross-encoder `BAAI/bge-reranker-base` (первый запуск качает ~1 ГБ модели). Используется UI, MCP-сервером и eval.

Бит лекции «наивный вектор мажет по идентификатору → гибрид находит»:

```bash
# чистый вектор теряет точный идентификатор
uv run python retrieval.py "NominatedNodeName" --mode dense

# гибрид (BM25+вектор) ловит его; реранк поднимает точный фрагмент наверх
uv run python retrieval.py "NominatedNodeName" --mode hybrid --rerank

# вопрос «почему», скоуп по пласту
uv run python retrieval.py "why doesn't preemption guarantee the freed node" --mode hybrid --pile kep
```

Режимы: `--mode dense|sparse|hybrid`, фильтр `--pile code|kep|issue|docs`, `--top-k`, `--rerank`.

## Веб-интерфейс (UI): вопрос-ответ для человека

`app.py` (Streamlit) — путь RAG **без агента**: человек задаёт вопрос, система достаёт фрагменты и отвечает со ссылками. Тумблер «Использовать RAG» — контраст лекции: с RAG ответ заземлён в источниках и цитирует их; без RAG модель отвечает из своих весов, без ссылок.

```bash
uv run streamlit run app.py        # http://localhost:8501
```

Нужен `ANTHROPIC_API_KEY` в `.env` (ответ пишет Opus; русский вопрос переводится на английский для поиска через Haiku — корпус английский). Инфраструктура и индекс — из шагов Ф0–Ф1 выше; отдельно ничего экспортировать не нужно, `config.py` подхватывает `.env`.

## MCP-сервер (Ф3): RAG как инструмент агента

Кульминация лекции — RAG становится инструментом Claude Code (отсылка к лекции MCP). `mcp_server.py` (FastMCP) отдаёт инструмент `search_org_memory(query, pile?, top_k)` поверх `retrieval.py`.

```bash
# зарегистрировать сервер в Claude Code (stdio)
claude mcp add --transport stdio scheduler-memory -- uv run python mcp_server.py

# в Claude Code: /mcp  → должен появиться search_org_memory
```

Killer-демо (фича поверх вытеснения, с/без RAG): попросите агента спроектировать через скилл `design` (как в SDD) размещение помощника `H` (локальный кеш) на **той же ноде**, что и важный под `P`, которого планировщик метит на освобождённую ноду через `nominatedNodeName`.
- **Без** `search_org_memory` агент считает `nominatedNodeName` гарантией → «сажаем H на эту ноду сразу». Код по такому `design` ломается на гонке (P не занял ноду, H сидит там один).
- **С** инструментом — достаёт из `pod-preemption.md`, что `nominatedNodeName` лишь **подсказка** (со ссылкой), и `design` меняется на корректный: ждать фактической привязки P → тогда сажать H рядом. RAG изменил `design` → и **код, который поедет в прод**. Полный сценарий — в [`DEMO.md`](DEMO.md).

> Для killer-демо в корпусе нужен `kubernetes/design-proposals-archive/scheduling/pod-preemption.md` — добавляется в пласт `kep` на Ф5.

## Живое обновление (Ф4): очередь Redis Streams

Как в проде: событие → очередь → воркер индексирует → точка появляется на карте Qdrant → агент сразу достаёт. Redis уже поднят в `docker compose`.

```bash
# воркер: consumer-group читает stream, индексирует, XACK
uv run python worker.py

# приёмник GitHub-вебхуков (issues / issue_comment / pull_request) → XADD
uv run uvicorn webhook:app --port 8000

# демо без публичного URL — опубликовать вручную:
uv run python enqueue.py 124978        # переиндексировать issue/PR #124978
```

Поток: `webhook.py` (или `enqueue.py`) кладёт `{type:issue, ref:N}` в stream `scheduler-memory:index` → `worker.py` (`ingest.index_issue_number`) тянет issue с GitHub, чанкует, эмбедит, апсертит в Qdrant. Идемпотентно по `path` (повторы не плодят дубли). Ошибка оставляет сообщение в pending — `XPENDING scheduler-memory:index indexers` показывает durability «как в проде».

## Killer-демо + оценка (Ф5)

**Killer-демо (с/без RAG)** — кульминация лекции, полный сценарий в [`DEMO.md`](DEMO.md). Коротко: агента просят спроектировать фичу поверх вытеснения (артефакт `design` из SDD) — посадить помощника `H` на ту же ноду, что и под `P`. Без `search_org_memory` агент считает `nominatedNodeName` гарантией и проектирует код, который ломается на гонке; с ним — достаёт из `pod-preemption.md`, что это лишь подсказка, и `design` (а значит и код в проде) становится корректным. RAG меняет **проектное решение и то, что построят**. Требует `download_designs.py` в корпусе.

**Retrieval-eval** — измеряем слой ретривала «не на глаз» (вопрос → ожидаемые источники → hit-rate/precision/recall/MRR), датасет `eval_dataset.json`:

```bash
uv run python evaluate.py --mode dense              # базлайн
uv run python evaluate.py --mode hybrid --rerank    # сравнить: гибрид+реранк должен быть выше
```

## Карта знаний

Откройте Qdrant Dashboard: **http://localhost:6333/dashboard** → коллекция `scheduler_memory` → вкладка **Visualize** и запустите:

```json
{
  "limit": 1000,
  "using": "dense",
  "color_by": { "payload": "pile" }
}
```

`using: "dense"` обязателен — у коллекции именованные векторы `{dense, sparse}`, дефолтного нет (без него — ошибка «Please select a valid vector name»). Точки раскрасятся по четырём пластам — визуальная карта орг-памяти, открытие лекции.

## Архитектура (Ф0–Ф1)

```
download_*.py  →  data/{code,kep,issue,docs}/
                        │
                  index.py: chunk (по типу) → embed (dense Ollama + sparse BM25) → upsert
                        │
                  Qdrant: коллекция scheduler_memory, named vectors {dense, sparse}, payload {pile,path,...}
```

- Чанкинг (`chunking.py`): код — tree-sitter Go по символам; KEP/доки — markdown по заголовкам; issue — тело + каждый комментарий.
- Эмбеддинги (`embeddings.py`): dense — Ollama `nomic-embed-text` (768d); sparse — fastembed `Qdrant/bm25`.
- Хранилище (`store.py`): одна коллекция, dense+sparse под гибрид (Ф2). Идемпотентность по `uuid5(pile,path,index)`.
- Инкрементальность: хеши файлов в `data/.state.json`; повторный `index.py` индексирует только изменённое.
