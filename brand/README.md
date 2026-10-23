# Иконка SkrepNet

Вертикальная скрепка на фоне в цветах Telegram: `#5BC8F5 → #2AABEE → #1479B8`.
Круглая версия — для аватара бота, квадратная — для сайта.

## Что где лежит

| Файл | Назначение |
|---|---|
| `png/skrepnet-clip-512.png` | аватар бота для Telegram (загружать этот файл) |
| `png/skrepnet-clip-256/128/64/32.png` | уменьшенные копии для писем, презентаций, соцсетей |
| `svg/skrepnet-clip.svg` | исходник круглой иконки (вектор) |
| `svg/skrepnet-favicon.svg` | исходник квадратной иконки сайта |
| `png/skrepnet-favicon-*.png` | квадратные растровые версии, в том числе 180 px для iOS |
| `png/favicon.ico` | иконка для браузеров (16–64 px) |
| `png/skrepnet-cover-1280x640.png` | обложка для поста/канала |
| `png/og-image-1200x630.png` | превью ссылки (Open Graph, Twitter) |
| `png/skrepnet-icon-maskable-512.png` | PWA-иконка с запасом под маску Android |
| `preview.png` | сравнение вариантов |
| `mockup.png` | как иконка выглядит в боте и на сайте |
| `export.py` | пересборка PNG из SVG |

## Как поставить аватар бота

1. Открыть бота в Telegram → «Изменить информацию о боте» (или BotFather → `/setuserpic`).
2. Загрузить `png/skrepnet-clip-512.png`.
3. Telegram сам обрежет картинку в круг — запас по краям уже заложен.

## Как иконка подключена на сайте

Файлы лежат в `web/static/`:

- `favicon.ico`, `favicon.svg`, `favicon-16/32/48.png`
- `apple-touch-icon.png`
- `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`
- `site.webmanifest`
- `og-image.png`

Ссылки добавлены в шаблоны `docs.html`, `error.html`, `invite.html`, `miniapp.html`.
На странице подписки (`invite.html`) иконка также показывается в шапке карточки,
а в `<head>` прописаны Open Graph-теги для красивого превью ссылки.

Страница `sub_templates/skrepnet/index.html` живёт отдельно от Flask-приложения.
Иконка встроена в неё напрямую (inline SVG и favicon через data URI), поэтому
дополнительные файлы рядом с этой страницей не нужны.

## Обложка и превью ссылки

- `png/skrepnet-cover-1280x640.png` — широкая обложка. Используется в шапке
  README, подходит для поста канала или баннера.
- `png/og-image-1200x630.png` — картинка для превью ссылки. Файл уже скопирован
  в `web/static/og-image.png`, шаблон `invite.html` подставляет его в `og:image`.
- `svg/skrepnet-cover.svg` — исходник обложки.

## GitHub Social Preview

Готовую картинку `png/og-image-1200x630.png` можно загрузить вручную:
Settings → Social preview. Через GitHub API социальное превью не загружается.

## PWA

`web/static/site.webmanifest` описывает установку сайта как приложения:
иконки 192 и 512 px, maskable-версия, цвета темы и фона, `start_url = /miniapp`.
Для установки нужен HTTPS; поведение «Добавить на экран» зависит от браузера.

## Пересборка PNG

Нужны Python, Pillow и установленный Chrome (или Edge):

```powershell
python brand/export.py
```

Скрипт рендерит SVG в 512 px, обрезает круглые версии по кругу, собирает
`favicon.ico`, обложку и OG-картинку.

## Палитра

- Фон: `#5BC8F5` → `#2AABEE` → `#1479B8`
- Знак: `#FFFFFF`
- Акцент (в других вариантах): `#FFE2A8` → `#DFA24A`
