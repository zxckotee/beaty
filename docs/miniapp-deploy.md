# Telegram Mini App на betwelc.ru

## Требования

- HTTPS на публичном домене (Let's Encrypt на хостовом nginx, без балансировщика Timeweb)
- `PUBLIC_HTTPS_URL=https://betwelc.ru` и `PUBLIC_WEB_URL=https://betwelc.ru` в `.env.prod` / GitHub Secret
- `TENANT_UI_MODE=both` — чат-бот и кнопка «Открыть кабинет»
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

После мержа — redeploy; в `.env.prod` появятся `WEBHOOK_BASE_URL`, `PUBLIC_WEB_URL`, `TENANT_UI_MODE`, `WEB_COOKIE_SECURE`.

## Бот салона

1. У тенанта должен быть привязан токен бота (`bot_username` в БД).
2. В чате появляется кнопка **«Открыть кабинет»** (Web App) при `TENANT_UI_MODE=both`.
3. Опционально в **BotFather** → *Menu Button* → URL `https://betwelc.ru/t/<public_id>/`.

## Проверка Mini App

1. Открыть бота салона в Telegram.
2. Нажать «Открыть кабинет» — загружается SPA, вход по `initData` без poll-login.
3. В обычном браузере `https://betwelc.ru/t/<public_id>/` — прежний вход через «Войти через Telegram».