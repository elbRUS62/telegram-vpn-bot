# Внешний мониторинг SkrepNet

## Что проверяется

На каждом сервере работает отдельный systemd-таймер `skrepnet-monitor.timer`.
Он запускает проверку раз в минуту.

- **GB** проверяет локальный `/health`: база, heartbeat бота и обе панели 3x-ui — GB и RU.
- **RU** проверяет публичный `/health` на GB и игнорирует собственную панель RU, чтобы не дублировать алерты.

Если проверка неуспешна 5 минут подряд, отправляется одно сообщение в Telegram.
После восстановления отправляется второе сообщение.

## Конфигурация

Файл: `/etc/skrepnet-monitor.env`, права `600`, владелец `root`.

```env
MONITOR_NAME=GB
MONITOR_TARGET=https://127.0.0.1:8443/health
MONITOR_INSECURE=1
MONITOR_FAIL_THRESHOLD=5
MONITOR_STATE=/var/lib/skrepnet-monitor/state.json
ALERT_BOT_TOKEN=...
ALERT_CHAT_IDS=123456789,987654321
MONITOR_TIMEOUT=15
```

Для RU:

```env
MONITOR_NAME=RU
MONITOR_TARGET=https://gb-skrepnet.duckdns.org:8443/health
MONITOR_INSECURE=0
MONITOR_FAIL_THRESHOLD=5
MONITOR_STATE=/var/lib/skrepnet-monitor/state.json
MONITOR_IGNORE_PANELS=ru
ALERT_BOT_TOKEN=...
ALERT_CHAT_IDS=123456789,987654321
MONITOR_TIMEOUT=15
```

`ALERT_BOT_TOKEN` и `ALERT_CHAT_IDS` можно заменить на отдельного alert-бота и отдельный чат, не меняя логику.

## Установка

```bash
install -m 755 scripts/skrepnet-monitor.py /usr/local/sbin/skrepnet-monitor.py
install -d -m 700 /var/lib/skrepnet-monitor
install -m 600 /path/to/skrepnet-monitor.env /etc/skrepnet-monitor.env
install -m 644 scripts/skrepnet-monitor.service /etc/systemd/system/
install -m 644 scripts/skrepnet-monitor.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now skrepnet-monitor.timer
systemctl start skrepnet-monitor.service
```

Проверка:

```bash
systemctl list-timers skrepnet-monitor.timer
journalctl -u skrepnet-monitor.service -n 20 --no-pager
cat /var/lib/skrepnet-monitor/state.json
```

## Ограничение

Это независимый монитор на двух серверах, но не полностью внешний сервис.
Если одновременно недоступны оба сервера, алерт не отправится.
Для полной независимости дополнительно нужен UptimeRobot, Better Stack или
Healthchecks.io, который проверяет `/health` снаружи.
