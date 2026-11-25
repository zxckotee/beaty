# 2ГИС MapGL и Catalog (фаза 2)

Текущая продуктовая схема — **Leaflet + OSM** по координатам из ссылок 2ГИС; виджет firmsonmap выключен по умолчанию (`DGIS_FIRMSONMAP_EMBED`). Фаза 2 нужна, если требуется кастомный UI карты 2ГИС, 3D или обогащение координат без данных в URL.

## Когда включать

- Нет координат в ссылке 2ГИС, но есть `DGIS_CATALOG_API_KEY` → `fetch_firm_point` в [`dgis_catalog.py`](../backend/app/domain/services/dgis_catalog.py).
- Нужна интерактивная векторная карта на MapGL → `DGIS_MAPGL_KEY` + Map Tiles API (платная подписка 2ГИС).

## Catalog (обогащение точек)

```
GET https://catalog.api.2gis.com/3.0/items/byid?id={firm_id}&fields=items.point&key=...
```

Вызов из `update_landing` при `settings.dgis_catalog_api_key` и пустых `map_lat`/`map_lon` у записи.

## MapGL (замена iframe)

1. Подключить `https://mapgl.2gis.com/api/js/v1` (CSP: `script-src`, `connect-src` для тайлов).
2. Инициализировать карту с `DGIS_MAPGL_KEY`.
3. Маркеры по `dgis_locations`; `Clusterer` при >5 точках.
4. Отключать firmsonmap iframe, когда ключ задан и клиентский бандл загружен.

## Статус в репозитории

- Заготовка Catalog: `dgis_catalog.fetch_firm_point` (без ключа — no-op).
- MapGL на фронте **не подключён**; на профиле по умолчанию только OSM + ссылки в 2ГИС.