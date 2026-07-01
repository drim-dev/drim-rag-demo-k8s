# Killer-демо: вытеснение (с/без RAG)

Кульминация лекции. Показывает, что RAG меняет **выход разработки**, а не просто отвечает на вопросы: без доступа к орг-памяти агент реализует интуитивный, но **отвергнутый** подход; с `search_org_memory` достаёт рационал отказа и обходит его.

## Тема

Cross-node preemption / «гарантировать поду освобождённую ноду». Интуитивно: если высокоприоритетный под не влезает — вытесни кого-то и **посади преемптора на освобождённую ноду**, а если на одной ноде места нет — **ищи жертв по всему кластеру**. И то, и другое было **рассмотрено и отвергнуто**.

**Рационал отказа (то, что должен достать RAG):**
- Преемпция НЕ гарантирует поду ноду — это лишь `status.nominatedNodeName` как подсказка (гонки, под может уехать на другую ноду; нужную ноду может занять другой высокоприоритетный под).
- Cross-node preemption отвергнут: «exhaustive search ... prohibitively expensive in large clusters».

**Источник ретривала:** `kubernetes/design-proposals-archive/scheduling/pod-preemption.md` (разделы «Supporting Cross Node Preemption?», «Notes», «Alternatives Considered») + `keps/sig-scheduling/1923-prefer-nominated-node`. Запасной бит из того же файла — «preempt by QoS first» (тоже отвергнут).

## Подготовка

```bash
# корпус должен включать design-proposals (пятый источник)
uv run python scripts/download_designs.py
uv run python index.py --source kep --force

# зарегистрировать MCP-сервер в Claude Code
claude mcp add --transport stdio scheduler-memory -- uv run python mcp_server.py
```

## Сценарий

Дайте агенту задачу (Claude Code):

> «Допиши логику преемпции в kube-scheduler: при вытеснении гарантируй, что вытесняющий под будет запланирован на ноду, с которой мы убрали жертв. Если на одной ноде места не хватает — найди минимальный набор подов для вытеснения по всему кластеру.»

- **Без `search_org_memory`** (отключите/не регистрируйте сервер): агент реализует «гарантию освобождённой ноды» и кластерный поиск жертв — повторяет отвергнутый дизайн.
- **С `search_org_memory`**: агент вызывает инструмент, достаёт рационал из `pod-preemption.md`, объясняет, почему гарантия невозможна (nominatedNodeName — лишь подсказка) и почему cross-node не делают (стоимость на масштабе), и предлагает корректный подход.

Это контраст «с/без RAG» из eval-нити: RAG меняет решение агента.

## Проверка ретривала

Что нужный фрагмент вообще достаётся (иначе гвоздь не сработает):

```bash
uv run python retrieval.py "why doesn't preemption guarantee the freed node" --mode hybrid --rerank --pile kep
uv run python evaluate.py --mode hybrid --rerank      # сравнить с --mode dense
```
