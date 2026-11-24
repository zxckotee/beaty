# Карта 2ГИС в профиле тенанта

## Текущая модель (после PR #101)

| Поле | Назначение |
| --- | --- |
| `dgis_locations` (JSONB) | Список филиалов: `firm_id`, `dgis_url`, опционально `label`, `map_lon`, `map_lat`, `map_zoom` |
| `dgis_url`, `dgis_firm_id` | Синхронизируются с **первым** элементом `dgis_locations` (уведомления, FloorsJS) |
| `dgis_embed_html` | Legacy: iframe из конструктора; при сохранении ссылок очищается. До пересохранения всё ещё отдаётся в API |
| `map_*` | Координаты первого филиала; запасная OSM-карта, если виджет 2ГИС недоступен |

## Поток для менеджера

1. В профиле (Mini App) или studio — блок **«Адреса на карте 2ГИС»**.
2. Вставить одну или несколько ссылок вида `https://2gis.ru/…/firm/<id>`.
3. `PATCH /api/t/{id}/manager/landing` с `{ "dgis_locations": [{ "dgis_url": "...", "label": "..." }] }`.
4. Бэкенд (`normalize_dgis_locations`, `build_firmsonmap_embed_src`) собирает виджет [firmsonmap](https://widgets.2gis.com/) **без API-ключа**.
5. На профиле — **один** iframe; кнопки «Открыть в 2ГИС» по каждому филиалу.

## Legacy

- Миграция `016` переносит `dgis_url` + `dgis_firm_id` в `dgis_locations`.
- Поведение API при пустом `dgis_locations`: чтение из legacy полей (`landing_locations_from_row`).
- Старый ввод HTML iframe больше не принимается при сохранении; отображение legacy iframe до первого сохранения ссылок.

## Резервная карта (OpenStreetMap)

Если виджет 2ГИС не строится, но у филиалов есть координаты из URL (`map_lat`/`map_lon`), показывается Leaflet + OSM с **несколькими маркерами** (fit bounds).

## Фаза 2 (опционально)

См. [dgis-mapgl-phase2.md](dgis-mapgl-phase2.md) — MapGL, Catalog API, переменные `DGIS_MAPGL_KEY` / `DGIS_CATALOG_API_KEY`.