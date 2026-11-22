# Telegram Mini App на betwelc.ru

## Требования

- HTTPS на публичном домене (Let's Encrypt на хостовом nginx, без балансировщика Timeweb)
- `PUBLIC_HTTPS_URL=https://betwelc.ru` и `PUBLIC_WEB_URL=https://betwelc.ru` в `.env.prod` / GitHub Secret
- `TENANT_UI_MODE=miniapp` — основной интерфейс в Mini App, в Telegram кнопка «Открыть» (`setChatMenuButton`); чат без reply-меню. Режим `both` оставляет чат-меню и тот же пункт «Открыть»
- `WEB_COOKIE_SECURE=true` в prod (ставится автоматически при `PUBLIC_HTTPS_URL`)

## Nginx на VPS

Конфиг в репозитории: [deploy/nginx-betwelc.edge.conf](../deploy/nginx-betwelc.edge.conf).

```bash
cd /root/beaty
bash scripts/deploy-edge-nginx-betwelc.sh
sudo certbot --nginx -d betwelc.ru
sudo nginx -t && sudo systemctl reload nginx
```

Не поднимать `docker-compose.tls.yml` на этом сервере — порты 80/443 занимает хостовый nginx (swingfox + betwelc).

## SSL (certbot)

На VPS (один раз или при продлении):

```bash
cd /root/beaty
CERTBOT_EMAIL=your@email.com bash scripts/enable-ssl-betwelc.sh
```

Вручную:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d betwelc.ru
```

Опционально в **GitHub Secrets** задайте `CERTBOT_EMAIL` — deploy попытается выпустить/обновить сертификат (без интерактива). После успешного HTTPS обязательно добавьте `PUBLIC_HTTPS_URL=https://betwelc.ru` и redeploy.

Проверка:

```bash
curl -sI https://betwelc.ru/health
curl -sI "https://betwelc.ru/t/<tenant_public_id>/"
```

## GitHub Secrets

| Secret | Пример |
| --- | --- |
| `PUBLIC_HTTPS_URL` | `https://betwelc.ru` |
| `CERTBOT_EMAIL` | (опционально) email для certbot в deploy |

После мержа — redeploy; в `.env.prod` появятся `WEBHOOK_BASE_URL`, `PUBLIC_WEB_URL`, `TENANT_UI_MODE`, `WEB_COOKIE_SECURE`.

### Если в браузере «Подключение не защищено» после certbot

На одном VPS с **swingfox.ru** nginx на `:443` должен отдавать **свой** сертификат для `betwelc.ru` (SNI). Частая причина: в `betwelc.ru.conf` только `listen 80` (шаблон перезаписал правки certbot), и тогда на HTTPS прилетает сертификат swingfox.

Проверка с любой машины:

```bash
echo | openssl s_client -connect betwelc.ru:443 -servername betwelc.ru 2>/dev/null | openssl x509 -noout -subject
# должно быть: subject=CN = betwelc.ru
```

Починка на VPS (после `git pull`):

```bash
cd /root/beaty
bash scripts/deploy-edge-nginx-betwelc.sh   # подставит deploy/nginx-betwelc.edge.https.conf, если есть LE-серт
nginx -t && systemctl reload nginx
```

Открывайте **`https://betwelc.ru/t/<public_id>/`** или кнопку Web App в боте (корень `/` в production — 404, без списка салонов).

## Файл `.env.prod` на VPS

Секреты БД и JWT лежат в `.secrets.env` (создаётся один раз). Публичный prod для betwelc:

```bash
cd /root/beaty
TELEGRAM_SECRET='<токен платформенного бота>' \
PUBLIC_HTTPS_URL=https://betwelc.ru \
bash scripts/write-env-prod-betwelc.sh
```

Проверка:

```bash
grep -E '^(WEBHOOK_BASE_URL|PUBLIC_WEB_URL|WEB_COOKIE_SECURE|TENANT_UI_MODE)=' .env.prod
./scripts/redeploy.sh nobuild
```

В репозитории: **[deploy/env.prod](../deploy/env.prod)** — эталон prod для betwelc.ru (секреты — плейсхолдеры). На VPS:

```bash
TELEGRAM_SECRET='...' bash scripts/install-env-prod.sh /root/beaty
# или CI: TELEGRAM_SECRET=... PUBLIC_HTTPS_URL=https://betwelc.ru bash scripts/write-env-prod-betwelc.sh
```

## Бот салона

1. У тенанта должен быть привязан токен бота (`bot_username` в БД).
2. В чате появляется кнопка **«Открыть кабинет»** (Web App) при `TENANT_UI_MODE=both`.
3. Опционально в **BotFather** → *Menu Button* → URL `https://betwelc.ru/t/<public_id>/`.

## Проверка Mini App

1. Открыть бота салона в Telegram.
2. Нажать «Открыть кабинет» — загружается SPA, вход по `initData` без poll-login.
3. В обычном браузере `https://betwelc.ru/t/<public_id>/` — прежний вход через «Войти через Telegram».