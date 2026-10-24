# CI и отслеживание ошибок

## Проверки вручную

Все проверки собраны в одном скрипте:

```bash
bash scripts/ci.sh
```

Скрипт:

- компилирует Python-код;
- запускает тесты на временной базе, не трогая рабочую;
- проверяет синтаксис `web/static/*.js` через `node --check`;
- подставляет тестовые значения переменных окружения, поэтому не требует `.env`.

На сервере скрипт можно запускать перед деплоем. Для автоматической проверки
перед `git push` можно добавить локальный хук:

```bash
cat > .git/hooks/pre-push <<'EOF'
#!/bin/bash
set -e
cd "$(git rev-parse --show-toplevel)"
bash scripts/ci.sh
EOF
chmod +x .git/hooks/pre-push
```

## GitHub Actions

Файл workflow: `.github/workflows/ci.yml`. Он запускает те же проверки на
каждый push в `main` и на pull request.

Важно: GitHub принимает изменения в `.github/workflows/*` только от токена
с правом `workflow`. Если токен без этого права, push отклоняется с ошибкой
`refusing to allow a Personal Access Token to create or update workflow`.

Варианты:

1. Создать новый classic PAT с правами `repo` и `workflow`, обновить
   `/root/.git-credentials` и запушить workflow обычным способом.
2. Добавить файл вручную через веб-интерфейс GitHub:
   `Add file` → `Create new file` → `.github/workflows/ci.yml`,
   вставить содержимое из репозитория.

До этого CI можно запускать вручную через `scripts/ci.sh`.

## Sentry или GlitchTip

Поддерживается любой сервис с Sentry-совместимым DSN. Интеграция
необязательная: без DSN приложение работает как раньше.

### Настройка

Добавить в `/root/skrepnet-bot/.env`:

```env
SENTRY_DSN=https://<key>@<host>/<project>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_RATE=0
```

- `SENTRY_DSN` — DSN проекта.
- `SENTRY_ENVIRONMENT` — окружение, по умолчанию `production`.
- `SENTRY_TRACES_RATE` — доля трассировок от `0` до `1`. Для начала `0`.

После изменения `.env` перезапустить сервисы:

```bash
systemctl restart skrepnet-bot skrepnet-web
```

Проверка отправки:

```bash
cd /root/skrepnet-bot
./venv/bin/python - <<'PY'
import sentry_sdk
from observability import init_sentry

if init_sentry("test"):
    sentry_sdk.capture_message("SkrepNet: тестовое событие")
    sentry_sdk.flush(timeout=10)
    print("отправлено")
else:
    print("SENTRY_DSN не задан")
PY
```

### Что отправляется

- необработанные исключения бота и веба;
- ошибки уровня `ERROR` из логов;
- тег `component` (`bot` или `web`), версия `skrepnet@<версия>`;
- окружение.

### Что не отправляется

- `initData` Telegram, заголовки, куки и тело запросов;
- токен бота и секреты в URL;
- username, email и IP пользователя;
- содержимое сообщений.

Очистка выполняется в `observability.py` перед каждой отправкой. Тесты на
очистку: `tests/test_observability.py`.

### Ограничения

- Пока не включена трассировка производительности: сначала нужно накопить
  ошибки и понять их объём.
- Бесплатные тарифы Sentry ограничены квотой событий; при превышении события
  перестанут приниматься до следующего периода.
- Если Sentry недоступен, приложение продолжает работать: отправка выполняется
  в фоне и не блокирует обработку запросов.
