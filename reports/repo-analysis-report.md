# AI Coding Agent Orchestrator

PROJECT_SIZE: БОЛЬШОЙ (15 файлов с кодом)
ДОМЕН: Автоматизация / Backend / DevTools
СТЕК: Python 3.12, FastAPI, TaskIQ, Redis, SQLAlchemy, asyncio, aiogram, httpx, structlog, PostgreSQL, Docker, OpenCode CLI
КЛЮЧЕВЫЕ ТЕГИ ДЛЯ РЕЗЮМЕ: Python, FastAPI, async, automation, AI agents, GitHub API, Telegram Bot, Clean Architecture

---

## Одна строка — что делает проект

> «Система автоматически берёт задачу из GitHub Issues, разворачивает изолированный AI-агент (OpenCode) в чистом клоне репозитория, ведёт весь цикл разработки — от клонирования до Pull Request — и уведомляет разработчика через Telegram в реальном времени.»

Альтернативная формулировка для нетехнической аудитории: вместо того чтобы вручную запускать AI-ассистента, давать ему задачу, следить за процессом и самому создавать PR — система делает всё это автоматически при появлении нового issue.

---

## Контекст и проблема

Команды, использующие AI-кодинг-агентов (OpenCode, Claude Code и аналоги), сталкиваются с одним и тем же узким местом: каждая задача требует ручного вмешательства. Нужно клонировать репозиторий, создать ветку, запустить агента, описать ему задачу, дождаться ответа, при необходимости ответить на уточнения, а потом вручную создать коммит и PR. При 10–20 задачах в неделю это превращается в рутину, поглощающую несколько часов разработческого времени.

Отдельная проблема — параллельность. Запустить несколько AI-агентов одновременно без изоляции окружений невозможно: они будут конфликтовать по файловой системе, git-состоянию, портам.

Без этого инструмента: разработчик сам выполняет 8–10 ручных шагов на каждую задачу, агент и человек работают в одном репозитории без изоляции, уведомления об окончании задачи отсутствуют, параллельная обработка нескольких задач невозможна.

### Решение

Сервис подписывается на GitHub webhooks и при появлении нового issue автоматически:

> Ключевая идея: разработчик работает только в привычных интерфейсах — GitHub и Telegram. Вся технически сложная часть (клонирование, запуск, мониторинг SSE, управление процессами) скрыта за автоматизацией.

1. Помещает задачу в очередь (Redis + TaskIQ)
2. Клонирует репозиторий в изолированный workspace
3. Создаёт feature-ветку
4. Запускает отдельный процесс OpenCode-сервера на динамическом порту
5. Создаёт сессию и передаёт агенту контекст задачи
6. Слушает SSE-поток событий от агента
7. Если агент задаёт вопрос — публикует его как комментарий в GitHub и ждёт ответа разработчика
8. При ответе разработчика в GitHub — маршрутизирует его обратно в активную сессию агента
9. При завершении задачи (маркер `[TASK_COMPLETED]`) — делает коммит, push, создаёт PR
10. На каждом значимом этапе отправляет уведомления в Telegram

Система поддерживает до 3 параллельных задач (настраивается), изолируя каждую в собственном workspace, на собственном порту и с собственной OpenCode-сессией.

### Измеримый результат

- Скорость: ручной процесс (8–10 шагов, 15–30 мин) → полностью автоматизирован за секунды
- Параллельность: до `MAX_CONCURRENT_INSTANCES` (по умолчанию 3) одновременных изолированных задач
- Надёжность: автоматический cleanup workspaces при ошибке или таймауте; retry-логика для файловых операций
- Покрытие тестами: 12+ E2E-сценариев, включая таймауты, ошибки агента, конкурентность, персистентность состояния
- [NEEDS VERIFICATION]: реальный выигрыш по времени в production-использовании

---

## Технический стек

### Языки и фреймворки

| Компонент | Технология | Зачем |
|-----------|-----------|-------|
| Web-сервер | FastAPI + Uvicorn | Принём GitHub webhooks, HMAC-верификация |
| Task queue | TaskIQ + Redis Streams | Асинхронная обработка задач вне HTTP-цикла |
| AI-агент | OpenCode CLI (subprocess) | Выполнение кодинговых задач |
| Telegram | aiogram 3.x | Уведомления и управление задачами через бота |
| GitHub | httpx + GitHub REST API v2022-11-28 | Комментарии к issues, создание PRs |
| Git | asyncio subprocess → git CLI | Clone, branch, commit, push |
| БД | SQLAlchemy AsyncIO + SQLite/PostgreSQL | Хранение состояния задач |
| Конфигурация | Pydantic Settings | Типизированные env-переменные |
| Логирование | structlog (JSON) | Структурированные логи с контекстом |

### Инфраструктура и деплой

Multi-stage Docker образ (python:3.12-slim) с non-root пользователем (`orchestrator`), healthcheck (`curl /health` каждые 30 сек) и exposed портом 8000. Worker и App — отдельные контейнеры с общим volume для workspaces (`/tmp/workspaces`). Docker socket монтируется в Worker-контейнер (`/var/run/docker.sock`) для возможности управления дочерними процессами.

Dev-окружение: `docker-compose.dev.yml` с profiles, SQLite вместо PostgreSQL, `--reload` для hot-reload. Production: `docker-compose.yml` с PostgreSQL 16, Redis 7, healthcheck'ами перед стартом app. Worker ограничен 2GB RAM (`mem_limit: 2G`), restart policy `unless-stopped`.

### Внешние интеграции

- GitHub REST API — webhooks (входящие), Issues API, Pull Requests API
- Telegram Bot API — уведомления о ходе задачи, команды `/status`, `/list`, `/cancel`
- OpenCode сервер — локальный HTTP (REST + SSE), динамический порт на `--port 0`
- Redis — message broker для TaskIQ очереди

---

## Архитектура

### Компоненты системы

```
[GitHub Webhook] ──POST──► [FastAPI / router.py]
                                    │ HMAC verify
                                    ▼
                         [Redis Queue (TaskIQ)]
                                    │
                                    ▼
                          [Worker / broker.py]
                          asyncio.Semaphore(3)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              [GitCLIClient]  [GitHubAPIClient]  [OpenCodeProcessManager]
              clone/branch/   post_comment/      spawn_server(port=0)
              commit/push     create_pr          kill_server
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
                     [execute_coding_task use case]
                          │
                          ├─► [OpenCodeClient] ──SSE──► listen_events()
                          │         │
                          │    session.idle ──► [TASK_COMPLETED]?
                          │         │               │
                          │       Нет             Да
                          │         │               │
                          │   post_comment     commit + push
                          │   WAITING_REPLY    create_pr → DONE
                          │         │
                          │   [GitHub comment от user]
                          │         │
                          │   [handle_reply use case]
                          │         │
                          │   send_reply → RUNNING
                          │
                          └─► [TelegramNotifier] уведомления
                    
               [StateRepository / SQLAlchemy]
               Хранит: port, session_id, status, workspace_path
               Составной ключ: (issue_number, repo_url)
```

### Ключевые алгоритмы и паттерны

**SSE-цикл с детектором завершения.** Основной цикл `execute_coding_task` слушает SSE-поток от OpenCode через `httpx.AsyncClient` в streaming-режиме. Аккумулирует текст ответа агента через события `message.part.updated`, детектирует завершение по маркеру `[TASK_COMPLETED]` при наступлении `session.idle`. Это позволяет агенту задавать вопросы (нет маркера → публикация в GitHub + ожидание) и продолжать после ответа.

**Human-in-the-Loop через GitHub.** Вопросы агента превращаются в GitHub-комментарии, ответы разработчика приходят обратно через webhook и маршрутизируются в активную сессию через `send_reply`. Это позволяет вести диалог с агентом без выхода из GitHub.

**Динамический port binding.** OpenCode-сервер стартует с `--port 0` (OS выбирает свободный порт), менеджер читает порт из stdout по regex `r"(?:port[:\s]+|:)(\d{4,5})"` с таймаутом 30 секунд.

**Async cleanup через AsyncExitStack.** Workspace-очистка и kill-сервера регистрируются как callbacks через `contextlib.AsyncExitStack`, гарантируя cleanup при любом исходе (ошибка, таймаут, отмена).

**Поддержка нескольких репозиториев.** Webhook-секреты перечислены через запятую в `GITHUB_WEBHOOK_SECRET`, задачи идентифицируются составным ключом `(issue_number, repo_url)`. Одна инсталляция может обслуживать неограниченное число репозиториев с разными секретами.

**Паттерн состояния через БД.** `TaskStatus` (Enum: PENDING, RUNNING, WAITING_REPLY, DONE, FAILED, ABORTED) персистируется в SQLite/PostgreSQL через `StateRepository`. Любой компонент (webhook-handler, worker, Telegram-бот) читает актуальное состояние задачи из БД, что позволяет горизонтально масштабировать обработчики без потери контекста.

**HMAC-верификация с мультисекретом.** Каждый входящий webhook проходит проверку HMAC-SHA256 против набора секретов (через запятую), что позволяет безопасно обслуживать несколько репозиториев с разными токенами без дополнительных endpoint'ов.

### Поток данных

```
GitHub Issue → Webhook (HMAC verify) → Redis Queue → Worker (семафор)
→ Git clone (isolated workspace) → OpenCode spawn (dynamic port)
→ Create session → Send prompt → SSE stream listen
→ [TASK_COMPLETED]: commit → push → GitHub PR → Telegram notify → Cleanup
→ [Question]: GitHub comment → wait webhook → send_reply → continue SSE
→ [Timeout/Error]: GitHub comment → Telegram notify → Cleanup → ABORTED/FAILED
```

Состояние задачи на каждом переходе персистируется в БД:

| Этап | TaskStatus | active_port | session_id |
|------|-----------|-------------|------------|
| Webhook получен | PENDING | null | null |
| Клон + агент запущен | RUNNING | 54321 | null |
| Сессия создана | RUNNING | 54321 | abc-123 |
| Агент задаёт вопрос | WAITING_REPLY | 54321 | abc-123 |
| Пользователь ответил | RUNNING | 54321 | abc-123 |
| PR создан | DONE | null | null |
| Таймаут / ошибка | ABORTED / FAILED | null | null |

---

## Метрики кода

| Показатель | Значение |
|-----------|---------|
| Файлов с кодом (Python, без тестов и `__init__`) | 15 |
| Строк кода — приложение (Python) | ~1 410 |
| Строк кода — тесты (Python) | ~1 635 |
| Строк кода — скрипты (bash) | ~2 577 |
| Итого строк кода | ~5 600 |
| Наличие тестов | Да |
| Покрытие сценариев тестами | 12+ E2E-сценариев |
| Тип архитектуры | Clean Architecture (Presentation / Application / Domain / Infrastructure) |
| Документация | README, DEPLOYMENT.md, E2E_TESTING_GUIDE, openapi.json, Swagger через FastAPI |

---

## Бизнес-ценность и целевые клиенты

### Кому это нужно

- **Технические основатели и solo-разработчики**, использующие AI-агенты для ускорения разработки: хотят максимально автоматизировать цикл issue → PR, не тратить время на рутину
- **Небольшие технические команды (2–10 человек)**, внедряющие AI-ассистентов в workflow: нужна оркестрация без enterprise-инструментов
- **Фрилансеры с несколькими параллельными проектами**: автоматизация разгружает от ручного переключения контекстов
- **DevOps-инженеры и архитекторы**, строящие внутренние платформы разработки с AI-компонентами

### Боль, которую закрывает

Раньше: нужно вручную прочитать issue, открыть терминал, клонировать репозиторий, создать ветку, запустить AI-агента, дождаться ответа, при вопросе — скопировать вопрос и ответ, снова дождаться, потом вручную создать коммит и PR. На 10 задач в неделю — 3–5 часов ручной работы.

Теперь: разработчик получает Telegram-уведомление «PR создан» и только ревьюирует результат. Если агент задаёт вопрос — отвечает прямо в GitHub-комментарии.

### Альтернативы на рынке

- **GitHub Actions с Claude/GPT**: нет HITL-диалога, нет управления сессиями, агент отвечает в одном HTTP-запросе
- **Devin / SWE-Agent**: SaaS, дорого (от $500/мес), нет локального контроля данных
- **Ручное использование Claude Code / OpenCode**: полная ручная работа, нет автоматизации webhook→PR
- **Данный проект**: self-hosted, бесплатный (кроме LLM), полный HITL-диалог, изолированные окружения, Telegram-управление

### Потенциальный ROI и применимость

Для команды из 2–3 разработчиков, обрабатывающей 20–30 задач в месяц:
- Экономия ~2–4 часов/неделю ручной работы по оркестрации задач
- При стоимости часа разработчика $30–80: $240–640/мес сэкономленного времени
- Стоимость внедрения: self-hosted, развёртывание за 1–2 часа по инструкции из DEPLOYMENT.md
- [NEEDS VERIFICATION]: реальный throughput в production-условиях

Для агентства или студии разработки, ведущей 5–10 клиентских репозиториев:
- Оркестратор позволяет одному разработчику управлять AI-агентами на всех проектах из единой точки (один Telegram-бот, один Redis)
- Потенциальная экономия: 5–10 часов/неделю на рутинных задачах (hotfixes, мелкие фичи, рефакторинг)
- Self-hosted: нет vendor lock-in, данные кода не покидают контур организации

---

## Формулировки для резюме

### Bullet points (формат: активный глагол + технология + результат)

- Разработал асинхронный Python-оркестратор (FastAPI + TaskIQ + Redis) для автоматизации цикла GitHub Issue → Pull Request через AI-агентов, заменив 8–10 ручных шагов полностью автоматическим пайплайном
- Реализовал Clean Architecture с явными интерфейсами (ABC) и dependency inversion, обеспечив независимую замену любого компонента (Git, GitHub API, OpenCode, Telegram) без изменения бизнес-логики
- Спроектировал Human-in-the-Loop механизм взаимодействия между AI-агентом и разработчиком через GitHub Comments + SSE-поток, позволяющий вести диалог с агентом без выхода из интерфейса GitHub
- Реализовал управление параллельным выполнением через `asyncio.Semaphore`, обеспечив запуск до 3 изолированных AI-агентов одновременно с гарантированным cleanup через `AsyncExitStack`
- Автоматизировал жизненный цикл OpenCode-процессов: динамический port binding, чтение порта из stdout по regex с таймаутом, graceful shutdown с cross-platform kill
- Внедрил E2E-тестовое покрытие: 12+ сценариев (успех, таймаут, ошибки агента, конкурентность, персистентность состояния) с реалистичными mock-компонентами и <10 секунд полного прогона
- Спроектировал двусторонний SSE-цикл с аккумулятором текста, детектором маркера завершения и idle-таймаутом — обеспечив надёжное взаимодействие с LLM-агентом в streaming-режиме
- Реализовал систему Telegram-управления задачами (aiogram 3.x): команды `/list`, `/cancel`, авторизация по owner_id, форматирование статусов с emoji — без написания собственного UI

### Короткое описание для секции «Проекты»

**AI Coding Agent Orchestrator** — self-hosted сервис, автоматизирующий полный цикл разработки от GitHub Issue до Pull Request с участием AI-агента (OpenCode). Стек: Python 3.12, FastAPI, TaskIQ, Redis, SQLAlchemy, aiogram, Docker. Реализует Human-in-the-Loop диалог через GitHub Comments, поддерживает до 3 параллельных изолированных задач и полный lifecycle-менеджмент AI-процессов.

### Кейс для портфолио (боль → решение → результат)

ПРОБЛЕМА: Разработчики, использующие AI-агентов (OpenCode, Claude Code), тратят 15–30 минут ручной работы на каждую задачу: клонирование репозитория, запуск агента, мониторинг хода выполнения, создание коммита и PR. При росте объёма задач это становится серьёзным узким местом, а параллельный запуск нескольких агентов без изоляции окружений невозможен.

РЕШЕНИЕ: Разработан асинхронный Python-сервис на FastAPI с Clean Architecture. Сервис принимает GitHub webhooks, помещает задачи в Redis-очередь, запускает изолированные OpenCode-процессы в отдельных git-клонах на динамических портах, слушает SSE-поток событий от агента и ведёт двусторонний диалог через GitHub Comments. Telegram-бот обеспечивает real-time уведомления и управление задачами командами `/list`, `/cancel`.

РЕЗУЛЬТАТ: Весь процесс от появления GitHub Issue до создания Pull Request проходит автоматически без участия разработчика. Human-in-the-Loop диалог с агентом остаётся прямо в интерфейсе GitHub. Поддерживается параллельное выполнение до 3 задач с гарантированной изоляцией и автоматическим cleanup при любом исходе.

---

## Демонстрируемые навыки

| Категория | Навыки |
|-----------|-------|
| Языки | Python 3.12 (asyncio, dataclasses, ABC, generics) |
| Web-фреймворки | FastAPI, Uvicorn (ASGI) |
| Очереди задач | TaskIQ, Redis Streams |
| Базы данных | SQLAlchemy AsyncIO, PostgreSQL, SQLite |
| HTTP / API | httpx AsyncClient, GitHub REST API v2022-11-28, SSE |
| Telegram | aiogram 3.x (Bot, Dispatcher, FSM-команды) |
| DevOps | Docker (multi-stage), Docker Compose, Kubernetes-ready, healthchecks |
| Тестирование | pytest-asyncio, E2E-тесты с mock-компонентами, real integration tests |
| Архитектура | Clean Architecture, Repository Pattern, Dependency Inversion, AsyncExitStack |
| Логирование | structlog (JSON structured logs) |
| Конфигурация | Pydantic Settings, .env, multi-repo webhook secrets |

### Hard skills (для ATS-систем)

Python, FastAPI, asyncio, Redis, TaskIQ, SQLAlchemy, PostgreSQL, SQLite, Docker, Docker Compose, GitHub API, Telegram Bot API, aiogram, httpx, structlog, Pydantic, pytest, pytest-asyncio, Clean Architecture, REST API, SSE, Server-Sent Events, subprocess management, Git, GitHub webhooks, HMAC, CI/CD

### Soft skills / подходы, видные из кода

- **Тестирование**: 12+ E2E-сценариев с реалистичными моками — свидетельство TDD-подхода и внимания к граничным случаям
- **Инфраструктурная зрелость**: Docker multi-stage build, non-root user, healthcheck, Kubernetes-конфиги — DevOps-практики в разработке
- **Системное мышление**: AsyncExitStack для гарантированного cleanup, semaphore для контроля нагрузки — опыт надёжных распределённых систем
- **API-дизайн**: Clean Architecture с явными интерфейсами — проектирование под расширяемость и тестируемость
- **Cross-platform учёт**: retry-логика с chmod для Windows в cleanup — внимание к edge cases в production

---

## Ограничения и зоны роста

**Отсутствует:**
- **Unit-тесты**: только E2E; отдельные use cases и инфраструктурные компоненты не покрыты изолированными тестами, что усложняет точечную диагностику багов
- **Метрики и мониторинг**: нет Prometheus/Grafana, отсутствует observability для queue depth, latency агентов, error rate — в production невозможно отследить деградацию
- **Ротация логов**: JSON в stdout без агрегации; для production-использования нужен log shipper (Loki, ELK)
- **Авторизация webhook на уровне репозитория**: нет белого списка разрешённых репозиториев — любой репо с правильным секретом может запускать задачи

**Ограничения архитектуры:**
- **Привязка к OpenCode**: система заточена под один AI-агент; интеграция с Claude Code, Aider или другими потребует новой реализации `IOpenCodeProcessManager` — интерфейс определён, но адаптер нужно писать
- **PR всегда в `main`**: ветка-цель захардкожена, нет поддержки настройки base branch через конфиг или issue-теги
- **Distributed semaphore**: при горизонтальном масштабировании Worker'ов `asyncio.Semaphore` перестаёт работать — нужен Redis-based distributed lock (например, redlock)
- **OpenCode зависит от PATH**: CLI должен быть установлен на хосте; нет версионирования и fallback при отсутствии
- **HITL только через GitHub Comments**: нет альтернативного канала диалога с агентом (например, через Telegram напрямую)

**Технические долги:**
- `mypy` включён в strict-режиме в конфиге, но нет CI-проверки типов в workflow
- `base`-ветка для PR захардкожена как `"main"` без возможности конфигурирования
- Real-интеграционный тест (`test_opencode_real.py`) пропускается если OpenCode не установлен — нет CI-среды с реальным агентом
