# Карта 2ГИС в профиле тенанта

## Текущая модель (после PR #101)

| Поле | Назначение |
| --- | --- |
| `dgis_locations` (JSONB) | Список филиалов: `firm_id`, `dgis_url`, опционально `label`, `map_lon`, `map_lat`, `map_zoom` |
| `dgis_url`, `dgis_firm_id` | Синхронизируются с **первым** элементом `dgis_locations` (уведомления, FloorsJS) |
| `dgis_embed_html` | Legacy: iframe из конструктора; при сохранении ссылок очищается. До пересохранения всё ещё отдаётся в API |
| `map_*` | Координаты первого филиала; Leaflet/OSM на профиле |
| `dgis_embed_src`, `dgis_embed_probe_ok` | firmsonmap по умолчанию; probe отключает iframe при ошибке виджета |

## Поток для менеджера

1. В профиле (Mini App) или studio — блок **«Адреса на карте 2ГИС»**.
2. Вставить одну или несколько ссылок вида `https://2gis.ru/…/firm/<id>` (желательно с координатами в path: `…/firm/<id>/<lon>,<lat>`).
3. `PATCH /api/t/{id}/manager/landing` с `{ "dgis_locations": [{ "dgis_url": "...", "label": "..." }] }`.
4. На профиле — **интерактивная карта Leaflet + OpenStreetMap** по координатам филиалов; кнопки «Открыть в 2ГИС» по каждому филиалу.
5. Если `dgis_embed_probe_ok` — на лендинге **сначала** iframe [firmsonmap](https://widgets.2gis.com/) (клик по точке → карточка 2ГИС внутри виджета); иначе OSM по координатам из ссылки, клик по метке → `dgis_url`.

## Legacy

- Миграция `016` переносит `dgis_url` + `dgis_firm_id` в `dgis_locations`.
- Поведение API при пустом `dgis_locations`: чтение из legacy полей (`landing_locations_from_row`).
- Старый ввод HTML iframe больше не принимается при сохранении; отображение legacy iframe до первого сохранения ссылок.

## Карта на сайте (OpenStreetMap)

Основной интерактивный слой — Leaflet + OSM с **несколькими маркерами** (fit bounds), когда у филиалов есть `map_lat`/`map_lon` (из URL или Catalog API). Виджет firmsonmap **не используется по умолчанию** (`DGIS_FIRMSONMAP_EMBED` false).

## Фаза 2 (опционально)

См. [dgis-mapgl-phase2.md](dgis-mapgl-phase2.md) — MapGL, Catalog API, переменные `DGIS_MAPGL_KEY` / `DGIS_CATALOG_API_KEY`.