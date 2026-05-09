# Telegram Smart Home

Приложение для управления умным домом через Telegram, интегрированное с Home Assistant OS.

## Архитектура

Приложение использует модульную архитектуру для легкого масштабирования:

- `app.py`: Основной класс бота, обработка событий Telegram.
- `config.py`: Конфигурация устройств, организованная по категориям.
- `menus.py`: Классы для разных типов меню (свет, климат и т.д.).
- `keyboards.py`: Определение клавиатур.
- `helpers.py`: Вспомогательные функции.
- `rooms.py`: Функции для построения текста комнат.

## Добавление нового меню

1. Добавьте устройства в `config.py` в словарь `DEVICES`:

```python
DEVICES = {
    "lights": [...],
    "climate": [...],
    "doors": [
        ("Дверь 1", "lock.door1"),
        ("Дверь 2", "lock.door2"),
    ],
}
```

2. Создайте класс меню в `menus.py`:

```python
class DoorsMenu(Menu):
    def __init__(self, app):
        super().__init__(app, "doors")

    def get_text(self):
        text = "🚪 *Двери*\n\n"
        for name, entity in self.devices:
            state = self.app.get_state(entity)
            icon = "🔒" if state == "locked" else "🔓"
            text += f"{icon} {name}\n"
        return text
```

3. Добавьте в фабрику `get_menu`:

```python
menus = {
    "lights": LightsMenu,
    "climate": ClimateMenu,
    "doors": DoorsMenu,
}
```

4. Обновите `keyboards.py` и `app.py` для обработки новых команд.

## Запуск

Приложение запускается в AppDaemon для Home Assistant.