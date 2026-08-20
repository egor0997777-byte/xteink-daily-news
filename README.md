# Xteink Daily News

Автоматическая лента российских техновостей для **Xteink X3** (CrossPoint).

## Как подключить

В CrossPoint добавьте OPDS-каталог:

```
https://raw.githubusercontent.com/egor0997777-byte/xteink-daily-news/main/opds.xml
```

EPUB обновляется каждый день около **07:00 МСК**.

## Источники (тех / гик)

- Хабр (новости, статьи, разработка)
- Лайфхакер
- VC.ru
- iXBT
- 3DNews
- Tproger
- DTF

Только текст, без изображений.

В OPDS: «Все новости» + разделы по источникам (Хабр, Лайфхакер…).

## Как работает

1. GitHub Actions каждый день запускает `generate_news_epub.py`
2. Скрипт собирает RSS, дедуплицирует, чистит HTML
3. Собирает EPUB (общий + по источникам) без картинок
4. Обновляет `latest.epub`, `*.epub` и `opds*.xml`

Ручной запуск: Actions → Daily News EPUB → Run workflow
