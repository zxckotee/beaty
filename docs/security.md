# Безопасность Beaty (краткий чеклист)

## Секреты в production

Задайте сильные случайные значения (см. `scripts/write-env-from-ci.sh` → `.secrets.env`):

| Переменная | Назначение |
|------------|------------|
| `POSTGRES_PASSWORD` | БД (не менять без миграции тома) |
| `JWT_SECRET` | Access/refresh/web session JWT |
| `TOKEN_ENCRYPTION_KEY` | Шифрование токенов ботов в БД (ротация = потеря decrypt) |
| `PLATFORM_BOT_TOKEN` | Платформенный бот |
| `PLATFORM_TELEGRAM_WEBHOOK_SECRET` | Заголовок `X-Telegram-Bot-Api-Secret-Token` для `/tg/platform` |

Обязательно в production: `ENVIRONMENT=production`, `WEB_DEV_LOGIN=false`, `WEB_COOKIE_SECURE=true`.

## Webhook Telegram

- Платформа: секрет из `PLATFORM_TELEGRAM_WEBHOOK_SECRET` (не хардкод).
- Салоны: у каждого `tenant.webhook_secret` (миграция `017` заполняет пустые).
- Без секрета endpoint отвечает **503**, неверный секрет — **403**.

## Публичный REST `/api/v1`

По умолчанию выключен (`ENABLE_PUBLIC_API=false`). JWT привязан к `tenant` в payload; cross-tenant запросы → **403**. Роли берутся из staff/client в БД для указанного салона, не только из JWT.

## Ротация секретов

- **JWT_SECRET**: все сессии и API-токены станут недействительны; пользователи перелогинятся.
- **TOKEN_ENCRYPTION_KEY**: уже сохранённые `bot_token_encrypted` не расшифруются — нужна повторная привязка ботов.

## Модель угроз (основное)

1. Подмена Telegram webhook без секрета.
2. Dev-login в production (`/auth/dev`, `/login`).
3. Stored XSS через карту 2ГИС — только allowlist iframe на бэкенде; фронт не вставляет сырой HTML.
4. IDOR в REST API при включении `ENABLE_PUBLIC_API`.

## Edge (nginx)

TLS + `Strict-Transport-Security` в [`deploy/nginx-betwelc.edge.https.conf`](../deploy/nginx-betwelc.edge.https.conf). Rate limit по IP на web-аутентификации опирается на `X-Forwarded-For` от reverse proxy.