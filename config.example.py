# Шаблон конфигурации. Скопируйте в config.py и опишите свои сущности.
#
# DEVICES — плоский список устройств. Обязательные поля: name, entity, type, room.
#   type   — категория из CATEGORIES; определяет, в каком меню появится устройство.
#   entity — id сущности Home Assistant. Для датчиков с несколькими показаниями
#            вместо строки передаётся dict (см. пример ниже) и ставится is_sensor.
#   timer_minutes — только для type="lights": через сколько минут горения прислать
#            уведомление. Это значение по умолчанию, из Telegram его можно менять
#            в меню «⏱ Таймеры» (переопределения хранятся в state.json).
#            Без этого поля свет не отслеживается.

DEVICES = [
    {
        "name": "🚪 Коридор",
        "entity": "switch.hallway_light",
        "type": "lights",
        "room": "hallway",
        "timer_minutes": 15,
    },
    {
        "name": "❄️ Кондиционер",
        "entity": "climate.bedroom_ac",
        "type": "climate",
        "room": "bedroom",
    },
    {
        # Датчик с двумя показаниями: рисуется в таблице «Датчики» меню климата
        "name": "🛁 Ванная",
        "entity": {
            "temperature": "sensor.bathroom_temperature",
            "humidity": "sensor.bathroom_humidity",
        },
        "type": "climate",
        "room": "bathroom",
        "is_sensor": True,
    },
    {
        "name": "💤 Спальня",
        "entity": "cover.bedroom_blinds",
        "type": "blinds",
        "room": "bedroom",
    },
    {
        "name": "🌤️ Погода",
        "entity": "weather.forecast_home",
        "type": "weather",
        "room": "outside",
    },
]

# Разделы меню. Кнопка каждой категории автоматически появляется в главном меню.
CATEGORIES = {
    "lights": {
        "title": "🏠 *Освещение*\n\n",
        "button_label": "💡 Свет",
    },
    "climate": {
        "title": "🌬 *Климат*\n\n",
        "button_label": "🌡 Климат",
    },
    "blinds": {
        "title": "🪟 *Шторы*\n\n",
        "button_label": "🪟 Шторы",
    },
    "weather": {
        "title": "🌤 *Погода*\n\n",
        "button_label": "🌤 Погода",
    },
}

# Сущность бризера (приточной вентиляции), управляемая из меню кондиционера
BREATHER_ENTITY = "fan.air_fresh"

LIGHT_MONITOR_CONFIG = {
    "group_notification_window": 5,  # Минуты, в течение которых уведомления группируются в одно
    "reconcile_interval": 60,        # Секунды между сверками уведомлений с реальным состоянием
}

# Границы и шаги для настройки таймеров света из Telegram
TIMER_CONFIG = {
    "min_minutes": 1,
    "max_minutes": 720,
    "steps": [-30, -5, 5, 30],  # Кнопки быстрой правки в меню таймеров
}

TELEGRAM_CONFIG = {
    "chat_id": None,               # None — берётся из первого входящего сообщения
    "bot_token": "ТВОЙ_ТОКЕН_БОТА",  # Нужен для нативных таблиц и надёжного удаления уведомлений
}
