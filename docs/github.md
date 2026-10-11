# GitHub Actions и Pages

1. Код размещается в akaemov/ai-intelligence-service-arc, основная ветка main.
2. Actions → «Исследование спроса» → Run workflow. parameters — JSON-объект, например:

```json
{"days":90,"compare_days":90,"cities":["Уфа","Стерлитамак","Салават"],"services":["marketing","advertising","ai","research"],"groups":["media","vacancies","procurement"],"max_requests":30,"max_pages":10,"max_seconds":180,"max_api_budget":0,"region":"Республика Башкортостан"}
```

3. Оставьте publish=false для подготовки отчёта без публикации. Проверки Python/TS и сбор запускаются; статусы источников доступны в Summary и артефакте public-research-report. Артефакт содержит только проверенный публичный JSON и сайт, не SQLite и кэш страниц. Даже артефакты следует считать доступными читателям репозитория.
4. Для разрешённой публичной публикации: Settings → Pages → Source: GitHub Actions; настройте approval/protection environment github-pages при необходимости. Запустите workflow с publish=true. Деплой допускается только при ≥3 успешных источниках, ≥2 группах и успешном канале закупок. Сейчас этот порог не достигнут; публикация будет пропущена.
5. Pages base автоматически /имя-репозитория/. Для собственного домена потребуется отдельно настроить base, DNS и Pages.

Необходимы стандартные права GitHub Actions contents:read, а для deploy pages:write и id-token:write. Персональный PAT для запуска текущего workflow не нужен. Секреты внешних сервисов не добавлены: базовый конвейер не использует LLM. GH_TOKEN среды агента не попадает в клиент или артефакт.

История и последняя версия публичных результатов сохраняются через Actions cache исключительно из web/public/data. Кэш может быть вытеснен; это не долговременный архив. Сбой сбора не заменяет последний результат. CI на push/pull_request выполняет тесты и сборку без внешнего сбора. GitHub workflow ещё должен быть проверен реальным выполнением на GitHub; локальная сборка не подтверждает Pages или Actions.
