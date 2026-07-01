# Killer-демо: design-артефакт, заземлённый орг-памятью (с/без RAG)

Кульминация лекции. Показывает, что RAG меняет **выход разработки**, а не просто отвечает на вопросы. Здесь выход — это **design-документ** (проектное решение). Без орг-памяти агент проектирует интуитивный, но **отвергнутый** подход; с `search_org_memory` он достаёт задокументированный рационал отказа и пишет честную секцию «Alternatives Considered» со ссылкой на источник.

## Связь с лекцией про SDD

Артефакт `design` и скилл `design-brainstorming` — те же, что в SDD-лекции (проектное решение → план → спецификация). SDD даёт **дисциплину** проектного решения; RAG делает его **умным** — заземляет шаг «2-3 подхода с трейд-оффами» и секцию «Alternatives Considered» в реальных прошлых решениях, которые агент иначе бы не знал. Корпус RAG (kube-scheduler) целиком **состоит из design-артефактов** — KEP и design-proposal с секцией «Alternatives Considered». Поэтому демо элегантно: RAG **над** design-доками → чтобы написать новый design-док.

## Тема

Cross-node preemption / «гарантировать поду освобождённую ноду». Интуитивно: если высокоприоритетный под не влезает — вытесни кого-то и **посади преемптора на освобождённую ноду**, а если на одной ноде места нет — **ищи жертв по всему кластеру**. И то, и другое было **рассмотрено и отвергнуто**.

**Рационал отказа (то, что должен достать RAG и вписать в «Alternatives Considered»):**
- Преемпция НЕ гарантирует поду ноду — это лишь `status.nominatedNodeName` как подсказка (гонки; под может уехать; нужную ноду может занять другой высокоприоритетный под).
- Cross-node preemption отвергнут: «exhaustive search … prohibitively expensive in large clusters».

**Источник ретривала:** `kubernetes/design-proposals-archive/scheduling/pod-preemption.md` (разделы «Potential Solution», «Notes», «Preemption order») + `keps/sig-scheduling/1923-prefer-nominated-node`. Запасной бит из того же файла — «preempt by QoS first» (тоже отвергнут).

## Подготовка

```bash
# корпус должен включать design-proposals (пятый источник) — проверено, что фрагмент достаётся
uv run python scripts/download_designs.py
uv run python index.py --source kep --force

# скилл design-brainstorming уже лежит в .claude/skills/ этого репозитория
# зарегистрировать MCP-сервер в Claude Code
claude mcp add --transport stdio scheduler-memory -- uv run python mcp_server.py
```

## Сценарий (два прогона)

Запускай Claude Code **в этой папке** (тут и скилл, и MCP). Клонировать kubernetes не нужно — пишем документ, а не Go-код.

Задача агенту:

> «Спроектируй cross-node preemption для kube-scheduler: при вытеснении гарантируй, что вытесняющий под будет запланирован на ноду, с которой убрали жертв; если на одной ноде места не хватает — ищи минимальный набор жертв по всему кластеру. Используй `design-brainstorming`: разбери 2-3 подхода с трейд-оффами и секцией «Alternatives Considered», результат запиши в `docs/designs/`.»

- **Без `search_org_memory`** (сервер не зарегистрирован): агент проектирует «гарантию освобождённой ноды» и кластерный поиск жертв как рабочий вариант — секция «Alternatives Considered» угадана или пуста. Повторяет отвергнутый дизайн.
- **С `search_org_memory`**: на шаге разбора подходов агент зовёт инструмент, достаёт рационал из `pod-preemption.md`, и его «Alternatives Considered» честно помечает cross-node как **отвергнутый** — с причиной («prohibitively expensive in large clusters») и ссылкой; объясняет, почему гарантия ноды невозможна (`nominatedNodeName` — лишь подсказка), и предлагает корректный подход.

Порядок для сцены: сначала «без» (наивный design), потом «с» (расплата). Разные чистые сессии. Ценность подаём через **провенанс**: с RAG альтернативы с цитатой и источником; без — угаданы. Это тот же честный тезис, что во врезке «худший для RAG случай».

## Проверка ретривала

Что нужный фрагмент достаётся (иначе гвоздь не сработает):

```bash
# точный рационал cross-node всплывает первым
uv run python retrieval.py "is cross-node preemption supported and why" --mode hybrid --rerank --pile kep
uv run python evaluate.py --mode hybrid --rerank      # сравнить с --mode dense
```

Проверено: инструмент `search_org_memory` на этот вопрос возвращает `pod-preemption.md` с фразой «prohibitively expensive in large clusters» первым (score ≈ 0.9).

## Мост в SDD-лекцию

Здесь мы **сеем** артефакт `design` и скилл `design-brainstorming` (лекция 10, RAG). В лекции 12 (SDD) это разворачивается в дисциплину «проектное решение → план → спецификация». Связка: *орг-память заземляет проектное решение — RAG меняет design, а design меняет то, что построят.*
