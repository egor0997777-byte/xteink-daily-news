# Xteink Daily News

Автоматическая лента российских новостей для **Xteink X3** (CrossPoint).

## Как подключить

В CrossPoint добавьте OPDS-каталог:

```
https://raw.githubusercontent.com/egor0997777-byte/xteink-daily-news/main/opds.xml
```

EPUB обновляется каждый день около **07:00 МСК**.

Прямая ссылка на книгу:

```
https://raw.githubusercontent.com/egor0997777-byte/xteink-daily-news/main/latest.epub
```

## Источники

- РИА Новости
- Lenta.ru
- Интерфакс
- РБК

## Как работает

1. GitHub Actions каждый день запускает `generate_news_epub.py`
2. Скрипт собирает RSS, дедуплицирует, чистит HTML
3. Собирает компактный EPUB без картинок
4. Обновляет `latest.epub` и `opds.xml` в репозитории

Ручной запуск: Actions → Daily News EPUB → Run workflow

Только стандартная библиотека Python. Без внешних зависимостей.
