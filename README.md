# beaty

Брендированный Telegram-ассистент для онлайн-записи в бьюти-бизнесах: барбершопах, салонах красоты, у частных мастеров (маникюр, косметология, тату и т. п.).

## Идея в двух словах

Бизнес создаёт своего бота в **@BotFather** и передаёт токен нашему платформенному боту. Через 5 минут у салона есть бот **под его собственным именем и брендом**, который:

- записывает клиентов на услуги к мастерам, переносит и отменяет записи;
- напоминает о визите и просит подтвердить его, что заметно снижает неявки;
- возвращает клиентов («пора снова на стрижку к Ивану?»);
- собирает отзывы, рассылает акции, ведёт курсы и абонементы;
- даёт менеджеру и мастерам кабинет прямо в чате бота (меню, inline-кнопки, сценарии FSM).

Клиент видит бот салона, а не чужой агрегатор, где рядом показывают конкурентов. Приложение ставить не нужно, регистрироваться на сайте тоже — весь интерфейс живёт в Telegram.

## Зачем это бизнесу

| Боль | Что даём |
| --- | --- |
| Администратор весь день отвечает в мессенджерах | Запись 24/7 без участия человека |
| Неявки | Напоминания с кнопкой «Подтверждаю», учёт неявок, предоплата |
| Клиенты не возвращаются | Персональные напоминания по интервалу каждой услуги |
| Агрегаторы размывают бренд | Свой бот, свои цвета, свой тон общения |
| Непонятно, сколько заработали | Выручка, загрузка мастеров, выплаты |

## Две стороны продукта

- **Платформенный бот (наш)** — для владельца бизнеса: подключение токена, брендирование, оплата подписки, поддержка.
- **Бот бизнеса (развёрнут нами по токену)** — для клиентов, мастеров и менеджеров. Роль определяется по Telegram-аккаунту: клиент видит запись, мастер — свой день, менеджер — весь салон. UI — Reply Keyboard + Inline Keyboard + FSM, без отдельного веб-приложения.

## Документация

- [docs/product.md](docs/product.md) — роли, пользовательские сценарии, жизненный цикл записи, пограничные случаи, ограничения Telegram.
- [docs/architecture.md](docs/architecture.md) — техническая архитектура, стек, модель данных, алгоритм слотов, уведомления, безопасность.
- [docs/business.md](docs/business.md) — позиционирование, монетизация, онбординг, юридические вопросы (152-ФЗ), метрики.
- [docs/roadmap.md](docs/roadmap.md) — этапы MVP / V1 / V2.

## Стек (кратко)

Python 3.12, aiogram 3, FastAPI, PostgreSQL, Redis, очередь задач (Taskiq). Один мультитенантный сервис на вебхуках обслуживает всех ботов. Подробности и причины выбора — в [docs/architecture.md](docs/architecture.md).

## Development

1. Скопируйте `.env.example` в `.env` и заполните `PLATFORM_BOT_TOKEN` при работе с Telegram.
2. `make up` — PostgreSQL, Redis, MinIO.
3. `make backend-install && make migrate` — зависимости и миграции Alembic.
4. `make dev-api` — API на http://localhost:8000 (OpenAPI: `/docs`).
5. `make test` / `make lint` — pytest, ruff, mypy.
6. `make seed` — демо-тенант (после миграций).
7. Webhook локально: tunnel на `8000`, `POST setWebhook` на `{WEBHOOK_BASE_URL}/tg/{tenant_public_id}` с заголовком secret.

Структура кода: `backend/app/` (domain, api, bot, platform_bot, workers), [docs/pilot-checklist.md](docs/pilot-checklist.md).

## Деплой

Workflow [.github/workflows/deploy.yml](.github/workflows/deploy.yml) запускается при пуше в `main` и вручную (Actions → CI/CD Deploy → Run workflow). Сначала проходят проверки из `ci.yml`, затем GitHub Actions подключается к серверу по SSH и:

1. клонирует или обновляет репозиторий в `/root/beaty` (`git reset --hard origin/<ветка>`);
2. собирает `.env.prod` скриптом [scripts/write-env-from-ci.sh](scripts/write-env-from-ci.sh);
3. поднимает стек скриптом [scripts/redeploy.sh](scripts/redeploy.sh) (`build` или `nobuild`) через [docker-compose.prod.yml](docker-compose.prod.yml) и ждёт ответа `/health`.

На сервере работают контейнеры проекта compose `beaty`: `postgres`, `redis`, `api` (при старте применяет миграции; наружу порт `WEB_PORT`, по умолчанию `4040`), `worker` (напоминания) и `platform-bot` (long polling). Отдельного контейнера с фронтендом нет. Поменять порт можно переменной `WEB_PORT` в `deploy.yml`.

Секреты репозитория:

| Секрет | Назначение |
| --- | --- |
| `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` | Подключение к серверу (порт 22). `SSH_HOST` также используется как публичный адрес API |
| `TELEGRAM_SECRET` | Токен платформенного бота |
| `TELEGRAM_PROXY` | Необязательно: прокси для Telegram API, например `socks5://user:pass@host:1080` |

`POSTGRES_PASSWORD`, `TOKEN_ENCRYPTION_KEY` и `JWT_SECRET` генерируются на сервере при первом деплое и хранятся в `/root/beaty/.secrets.env`. Не удаляйте этот файл: без `TOKEN_ENCRYPTION_KEY` не расшифруются сохранённые токены ботов, а без `POSTGRES_PASSWORD` не будет доступа к базе.

Webhook-боты салонов требуют HTTPS-домена; до его появления API доступен по `http://<SSH_HOST>:4040`, а платформенный бот работает через polling. Опциональный TLS — профиль [docker-compose.tls.yml](docker-compose.tls.yml) + Caddy.

### Логи и состояние на сервере

Код на VPS обновляет **только CI/CD** (GitHub Actions с deploy-токеном). Ручной `git pull` с HTTPS обычно падает с `Authentication failed` — это нормально: у каталога на сервере нет вашего GitHub-токена. Ветка в репозитории — **`main`**, не `master`.

После каждого деплоя [scripts/write-env-from-ci.sh](scripts/write-env-from-ci.sh) создаёт `.env.prod` и симлинки `.env` → `.env.prod`, `docker-compose.yml` → `docker-compose.prod.yml`, чтобы работали привычные команды:

```bash
cd ~/beaty
docker-compose logs -f --tail=200
docker-compose ps
```

Эквивалент без симлинков (и для локальной отладки prod-файлов):

```bash
scripts/logs.sh
scripts/compose-prod.sh ps
scripts/compose-prod.sh logs -f api
```
