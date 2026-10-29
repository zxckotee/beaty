# beaty

Брендированный Telegram-ассистент для онлайн-записи в бьюти-бизнесах: барбершопах, салонах красоты, у частных мастеров (маникюр, косметология, тату и т. п.).

## Идея в двух словах

Бизнес создаёт своего бота в **@BotFather** и передаёт токен нашему платформенному боту. Через несколько минут у салона есть бот **под его собственным именем и брендом**, который:

- записывает клиентов на услуги к мастерам (кнопки и inline-клавиатура в чате);
- переносит и отменяет записи, напоминает о визите с кнопкой «Подтверждаю»;
- возвращает клиентов («пора снова на стрижку?»), собирает отзывы, ведёт курсы и акции;
- даёт мастеру команды «мой день» и статусы визита, менеджеру — обзор дня и базовое управление каталогом.

**Клиент работает только в Telegram:** `/start`, контакт для телефона, дальше запись через inline-кнопки. Отдельное приложение, сайт и HTTPS-домен для записи **не нужны**.

Клиент видит бот салона, а не чужой агрегатор. Роль (клиент / мастер / менеджер) определяется по Telegram-аккаунту и привязке в базе.

## Зачем это бизнесу

| Боль | Что даём |
| --- | --- |
| Администратор весь день отвечает в мессенджерах | Запись 24/7 в боте без участия человека |
| Неявки | Напоминания с кнопкой «Подтверждаю», учёт неявок |
| Кliенты не возвращаются | Персональные напоминания по интервалу услуги |
| Агрегаторы размывают бренд | Свой бот, свой тон общения |
| Непонятно, сколько заработали | Выручка, загрузка мастеров (API и отчёты) |

## Две стороны продукта

| Компонент | Кто пользуется | Как запускается |
| --- | --- | --- |
| **Платформенный бот** | Владелец бизнеса | Long polling, сервис `platform-bot` |
| **Бот салона** | Клиенты, мастера, менеджеры | Long polling, сервис **`tenant-bots`** (все активные тенанты) |

Платформенный бот: онбординг, токен салонного бота, бренд, подписка. Бот салона: весь основной UX в чате (FSM, callback-кнопки, reply-меню).

Опционально (не для bot-only prod): [Mini App](miniapp/) и контейнер `web`, если `TENANT_UI_MODE=miniapp|both` и настроен HTTPS — см. [docs/product.md](docs/product.md).

## Документация

- [docs/product.md](docs/product.md) — роли, сценарии, жизненный цикл записи, bot-first UX.
- [docs/architecture.md](docs/architecture.md) — стек, данные, слоты, уведомления, безопасность.
- [docs/business.md](docs/business.md) — позиционирование, монетизация, 152-ФЗ, метрики.
- [docs/roadmap.md](docs/roadmap.md) — MVP / V1 / V2.
- [docs/pilot-checklist.md](docs/pilot-checklist.md) — чеклист пилота, в т. ч. bot-only.

## Стек (кратко)

Python 3.12, **aiogram 3** (polling), FastAPI (domain + REST), PostgreSQL, Redis, Taskiq (воркер уведомлений). Мультитенантность: один процесс `tenant-bots` опрашивает Telegram API для всех подключённых ботов салонов. Подробности — [docs/architecture.md](docs/architecture.md).

## Development

1. Скопируйте `.env.example` → `.env`, укажите `PLATFORM_BOT_TOKEN` (и при тесте салона — зашифрованный токен тенанта через онбординг).
2. `make up` — PostgreSQL, Redis, MinIO.
3. `make backend-install && make migrate`
4. `make dev-api` — API http://localhost:8000 (`/docs`).
5. Запуск ботов локально (отдельные терминалы):
   - `cd backend && python -m app.platform_bot.run_polling` — платформенный бот;
   - `cd backend && python -m app.bot.run_tenant_polling` — боты салонов с `bot_status=active`.
6. `make test` / `make lint` — pytest, ruff, mypy.
7. `make seed` — демо-тенант (после миграций).

Webhook и tunnel **не требуются** для bot-only. Переменная `TENANT_UI_MODE` по умолчанию `bot`.

Mini App (только если нужен legacy UI): `cd miniapp && npm install && npm run dev`, `VITE_API_BASE=http://localhost:8000`.

Структура: `backend/app/` (`domain`, `api`, `bot/`, `platform_bot/`, `workers`), опционально `miniapp/`.

### Команды в боте салона (кратко)

| Роль | Примеры |
| --- | --- |
| Клиент | `/start`, `/book`, `/my`, `/help`, `/cancel` |
| Мастер | `/day`, `/sick` |
| Менеджер | `/today`, `/staff`, `/pending`, `/service_add` |

## Деплой

Workflow [.github/workflows/deploy.yml](.github/workflows/deploy.yml) — push в `main` или ручной запуск. CI, затем SSH на сервер:

1. репозиторий в `/root/beaty` (`git reset --hard origin/<ветка>`);
2. `.env.prod` — [scripts/write-env-from-ci.sh](scripts/write-env-from-ci.sh);
3. стек — [scripts/redeploy.sh](scripts/redeploy.sh) + [docker-compose.prod.yml](docker-compose.prod.yml), проверка `/health`.

Контейнеры `beaty`:

| Сервис | Назначение |
| --- | --- |
| `postgres`, `redis` | Данные и callback-кэш |
| `api` | REST, миграции |
| `worker` | Планировщик и отправка уведомлений в Telegram |
| `platform-bot` | Онбординг владельца |
| **`tenant-bots`** | **Long polling всех ботов салонов (основной UX)** |
| `web` | Только при `TENANT_UI_MODE=miniapp\|both` |

Домен и TLS **не обязательны** для записи клиентов: они пишут `@YourSalonBot` в Telegram.

Секреты GitHub:

| Секрет | Назначение |
| --- | --- |
| `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` | SSH на сервер |
| `TELEGRAM_SECRET` | Токен платформенного бота |
| `TELEGRAM_PROXY` | Необязательно: прокси для Telegram API |

`POSTGRES_PASSWORD`, `TOKEN_ENCRYPTION_KEY`, `JWT_SECRET` — в `/root/beaty/.secrets.env` (не удалять).

### Логи на сервере

Деплой только через CI; ручной `git pull` по HTTPS часто падает без токена — это ожидаемо. Ветка — **`main`**.

```bash
cd ~/beaty
docker-compose logs -f --tail=200 tenant-bots
docker-compose ps
```

Или [scripts/logs.sh](scripts/logs.sh), [scripts/compose-prod.sh](scripts/compose-prod.sh).
