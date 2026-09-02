# ProtoeuroBot

Телеграм бот, позволяющий реализовать симулятор Евровидения.

Конкурс делится на 2 стадии: подачу заявок и голосование. Команда `/help` описывает все доступные пользователю команды на каждой стадии конкурса. Команда `/admin_help`, которая становится доступной после добавления вашего telegram id в `RAW_ADMIN_IDS`, позволяет ознакомиться с админскими командами для просмотра чужих заявок, рассылки сообщений участникам, удобной генерации таблиц с текущими результатами конкурса, и так далее.

## Структура репозитория

```mermaid
flowchart TD
  repo["📁 src"]

  rules["📁 rules"]
  entities["📁 entities"]

  database["📄 database.py"]
  protoeurobot["📄 protoeurobot.py"]
  utils["📄 utils"]
  web["📄 web.py"]

  contest_rules["📄 CONTEST_RULES.txt"]
  application_rules["📄 APPLICATION_RULES.txt"]
  voting_rules["📄 VOTING_RULES.txt"]

  application["📄 application.py"]
  herald["📄 herald.py"]
  points_table["📄 points_table.py"]
  vote["📄 vote.py"]

  repo --> rules
  repo --> database
  repo --> protoeurobot
  repo --> utils
  repo --> web
  repo --> entities

  rules --> contest_rules
  rules --> application_rules
  rules --> voting_rules

  entities --> application
  entities --> herald
  entities --> points_table
  entities --> vote
```

1. `rules` содержит правила контеста, которые смогут увидеть участники. В файлах содержатся ограничения по умолчанию.
2. `database` - реализация базы данных на основе `aiosqlite` и запросов через `pypika`.
3. `protoeurobot` - логика взаимодействия API telegram, реализована через `aiogram` и `asyncio`.
4. `web` - получение и обработка клипов для песен с YouTube через `aiohttp`.
5. `entities` - сущности и их вспомогательные методы, используемые в боте.
6. `utils` - вспомогательные методы.

## Использование

### Установка

```bash
uv pip install -e protoeuro_bot --force-reinstall
```

### Запуск
```
python protoeurobot.py
```

## Авторы
[Святослав Белкин](https://github.com/M3VV0)
