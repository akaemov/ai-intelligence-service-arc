# GitHub Actions и Pages

## Подготовленная публикация текущего отчёта

По запросу владельца собран и отправлен статический сайт в ветку `gh-pages` (коммит `0d53d699a4604cc1b762c4a5fad0c6f82ec0597b`). Включены проверенные обезличенные latest.json/attempt.json; внутренние SQLite, кэш и секреты исключены. Частичное покрытие явно показано, готовность исследования не заявляется.

GitHub API отклонил изменение visibility и включение Pages с `403 Resource not accessible by integration`; репозиторий остался private. Владельцу нужно:

1. Settings → General → Danger Zone → Change repository visibility → Public.
2. Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: gh-pages → / (root) → Save.
3. Дождаться успешного Pages build/deployment. Ожидаемый адрес после включения: https://akaemov.github.io/ai-intelligence-service-arc/ . До подтверждения деплоя это не действующая ссылка на сайт.

Эта ветка содержит снимок текущего отчёта; обновление сборщика само по себе её не обновляет. Для автоматизированной публикации следующего полноценного исследования переключите Pages Source на GitHub Actions и используйте workflow ниже. Частичный снимок опубликован в Git-ветку по отдельному явному запросу владельца; требования достаточного покрытия в research.yml сохранены.

## Автоматизированное исследование

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
