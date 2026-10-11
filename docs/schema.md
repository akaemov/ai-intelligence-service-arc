# Наблюдения v2

Единый тип `src/models.py:Observation`, строгая проверка типов и [JSON Schema](../schemas/observation.schema.json). `null` означает неизвестный факт. Ключевые поля:

| Группа | Поля |
|---|---|
| Происхождение | observation_id, run_id, source_name/type/url, canonical_url, published_at, collected_at, content_hash, dictionary_version |
| География | country, federal_district, customer_region/city, execution_geography, target_market_geography, contractor_search_geography, remote_delivery, geography_evidence/details |
| Заказчик | organization_name/size, customer_segment, industry |
| Запрос | service_category, signal_type/subtype, requested_service, customer_problem, requirements |
| Деньги | explicit_budget, budget_min/max, currency, budget_basis, price_type |
| Проверка | short_evidence_excerpt, factual_summary, analyst_interpretation, confidence_level/reason, limitations, federal_eligible, regional_eligible |
| Событие | event_id, duplicate_group_id, procurement_status, survey |

`region/city_or_district` — совместимые aliases географии заказчика. Бюджетный диапазон сохраняется двумя границами; средняя цена не рассчитывается. Валюты не суммируются. Зарплата и цена поставщика не становятся бюджетом заказчика. География исполнителя не становится регионом покупателя.

`federal_eligible` требует явного основания связи с Россией, даты в периоде, услуги и выбранного сегмента. `regional_eligible` дополнительно требует региона заказчика. Подтверждённое событие в Москве без покупателя может быть федеральным контекстом E, но не региональным спросом A.
