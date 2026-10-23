# Offsite-бэкапы и внешний uptime

Документ описывает настройку, которая уже подготовлена на сервере.

## Что настроено

- `restic` установлен на сервер.
- Создан отдельный пароль шифрования restic:
  `/root/.config/skrepnet-offsite/restic-password`
- Подготовлены скрипты:
  - `scripts/offsite-backup.sh` — проверяет последний локальный бэкап, отправляет его в Backblaze B2, применяет retention и отправляет heartbeat в UptimeRobot.
  - `scripts/offsite-check.sh` — проверяет целостность offsite-репозитория.
  - `scripts/offsite-restore-check.sh` — восстанавливает последний snapshot во временную папку и проверяет базу.
  - `scripts/send-alert.sh` — отправляет технические алерты в отдельный Telegram-бот.
- Подготовлены конфиги без секретов:
  - `/root/.config/skrepnet-offsite/offsite.env`
  - `/root/.config/skrepnet-alerts.env`

Секреты в git не добавляются.

## Backblaze B2

1. Создать приватный bucket, например `skrepnet-backups`.
2. Создать application key с доступом только к этому bucket.
3. Записать в `/root/.config/skrepnet-offsite/offsite.env`:
   - `AWS_ACCESS_KEY_ID` — key ID;
   - `AWS_SECRET_ACCESS_KEY` — application key;
   - `RESTIC_REPOSITORY` — например `s3:https://s3.us-west-004.backblazeb2.com/skrepnet-backups`.
4. Проверить, что файл доступен только root.

Пароль restic нужно сохранить в менеджере паролей или в офлайн-копии. Без него восстановление из B2 невозможно.

## Инициализация restic

После заполнения B2-переменных выполнить один раз:

`restic init`

Переменные окружения берутся из `offsite.env`, пароль — из `restic-password`.

## UptimeRobot

Создать два монитора:

1. HTTP-проверка `/health`:
   - URL: `https://gb-skrepnet.duckdns.org:8443/health`
   - интервал: 5 минут;
   - keyword: `"status":"ok"`;
   - алерт после 2 неудачных проверок.
2. Heartbeat для offsite-бэкапа:
   - период: 1 день;
   - grace: 2 часа;
   - URL записать в `UPTIMEROBOT_BACKUP_URL`.

Дополнительно можно создать heartbeat для ежемесячной проверки восстановления и записать его в `UPTIMEROBOT_RESTORE_URL`.

В Telegram-алерты UptimeRobot добавить отдельный чат или канал.

## Telegram-бот алертов

1. Создать отдельного бота через BotFather.
2. Записать токен в `/root/.config/skrepnet-alerts.env` в `ALERT_BOT_TOKEN`.
3. Добавить бота в чат или канал и записать ID в `ALERT_CHAT_ID`.
4. Проверить отправку тестового сообщения.

## Cron

После заполнения конфигов добавить задачи:

```cron
15 3 * * * flock -n /var/lock/skrepnet-offsite.lock /root/skrepnet-bot/scripts/offsite-backup.sh >> /root/skrepnet-bot/backups/offsite.log 2>&1
30 6 * * 0 flock -n /var/lock/skrepnet-offsite-check.lock /root/skrepnet-bot/scripts/offsite-check.sh >> /root/skrepnet-bot/backups/offsite-check.log 2>&1
0 7 1 * * flock -n /var/lock/skrepnet-offsite-restore.lock /root/skrepnet-bot/scripts/offsite-restore-check.sh >> /root/skrepnet-bot/backups/offsite-restore.log 2>&1
```

Для защиты от параллельного запуска используется `flock`.

## Проверка восстановления

Ежемесячная проверка:

1. Скачать последний snapshot.
2. Проверить SHA-256 и `PRAGMA integrity_check`.
3. Проверить наличие обязательных таблиц.
4. Сравнить количество пользователей, приглашений и тикетов с локальной базой.
5. Удалить временную копию.

Раз в квартал полезно восстановить базу на отдельной тестовой машине и запустить копию web-процесса с тестовыми токенами.

## Что нельзя делать

- Загружать базу в B2 без шифрования.
- Хранить пароль restic только на том же сервере.
- Удалять локальные бэкапы до успешной проверки offsite-копии.
- Добавлять ключи B2 и токен алертов в git.
