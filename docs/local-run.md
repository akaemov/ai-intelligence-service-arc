# Локальный запуск

Python 3.11+ (проверено 3.12), Node 22+ (проверено 24), npm. Python использует только стандартную библиотеку.

```bash
cd /workspace/ai-intelligence-service-arc
npm --prefix web ci --ignore-scripts --cache /workspace/scratch/npm-cache
python -m unittest discover -s tests -v
npm --prefix web test
python -m src.run
npm --prefix web run build
npm --prefix web run dev -- --port 5173
```

Последняя команда запускает локальный сервер; он должен быть перезапущен в новой среде. Внешние preview-ссылки не нужны. Python exit 0 — успешны все выбранные адаптеры; 2 — частичный/неудачный сбор (отчёт существует); другие ошибки — конфигурация/неожиданное нарушение. Проверяйте статус, а не только код сборки.

```bash
python -m src.run --days 90 --compare-days 90 \
  --cities 'Уфа,Стерлитамак,Салават,Нефтекамск' \
  --services marketing,advertising,ai,research \
  --groups media,vacancies,procurement \
  --max-requests 30 --max-pages 10 --max-seconds 180 --max-api-budget 0
```

Регион этой версии фиксирован Башкортостаном, чтобы не выдавать непроверенное сопоставление других регионов. compare_days хранится как параметр запроса, но независимый сравнительный сбор пока отсутствует.

Внутреннее: .state/research.sqlite, .state/cache, .state/history.json, .state/runs/. Публичное: web/public/data/latest.json, attempt.json. Кэш HTTP 1 час; max_requests — реальные попытки HTTP, max_pages — загруженные страницы/API-страницы. Время ограничено, ответы до 10 MB (справочник HH превышает 2 MB), TLS и прокси остаются проверяемыми. Повторы только временных ошибок (не 403), интервалы не менее 1 секунды.

Последний успешный/частичный результат сохраняется при полном сбое. attempt.json показывает последнюю попытку отдельно. Файловая блокировка не допускает одновременно два конвейера в одном каталоге .state. JSON записывается атомарно. SQLite не экспортируется.

CSV/JSON экспортируются из фильтрованного реестра в браузере; CSV защищён от формул. Публичные строки проверяются на телефоны, email, известные токены, опасные поля/URL и существующие runtime-ключи. Этот фильтр не заменяет ручной обзор допустимости публикации.
