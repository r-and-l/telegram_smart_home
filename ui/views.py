from datetime import datetime
from prettytable import PrettyTable, TableStyle
import logging

def build_keyboard(items, per_row=3):
    keyboard = []
    row = []

    for i, item in enumerate(items, start=1):
        row.append(item)
        if i % per_row == 0:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    return keyboard


def build_device_extra_text(app, name, entity, state):
    """Возвращает дополнительную строку для устройства, например время работы."""
    if state != "on":
        return None

    last_changed = app.get_state(entity, attribute="last_changed")
    if not last_changed:
        return None

    try:
        changed_time = datetime.fromisoformat(last_changed.replace("Z", "+00:00"))
    except Exception:
        return None

    minutes = int((datetime.now(changed_time.tzinfo) - changed_time).total_seconds() / 60)
    return f"💡 {minutes} мин"


WEATHER_TRANSLATIONS = {
    "clear-night": "Ясно 🌃",
    "cloudy": "Облачно ☁️",
    "fog": "Туман 🌫️",
    "hail": "Град 🌨️",
    "lightning": "Гроза ⛈️",
    "lightning-rainy": "Гроза с дождем ⛈️",
    "partlycloudy": "Переменная облачность ⛅",
    "pouring": "Ливень 🌧️",
    "rainy": "Дождь 🌧️",
    "snowy": "Снег ❄️",
    "snowy-rainy": "Снег с дождем 🌨️",
    "sunny": "Ясно ☀️",
    "windy": "Ветрено 💨",
    "windy-variant": "Ветрено 💨",
    "exceptional": "Особые условия ⚠️"
}

MOON_PHASES = {
    "new_moon": "Новолуние 🌑",
    "waxing_crescent": "Растущий серп 🌒",
    "first_quarter": "Первая четверть 🌓",
    "waxing_gibbous": "Растущая луна 🌔",
    "full_moon": "Полнолуние 🌕",
    "waning_gibbous": "Убывающая луна 🌖",
    "third_quarter": "Последняя четверть 🌗",
    "waning_crescent": "Убывающий серп 🌘"
}

def build_sensor_extra_text(app, name, entity, state):
    """Возвращает форматированное значение сенсора на русском языке."""
    if state is None:
        return "нет данных"
        
    entity_lower = entity.lower()
    
    # 1. Weather entity
    if entity_lower.startswith("weather."):
        condition = WEATHER_TRANSLATIONS.get(str(state).lower(), str(state))
        
        # Extract temperature and humidity attributes
        temp = app.get_state(entity, attribute="temperature")
        humidity = app.get_state(entity, attribute="humidity")
        
        parts = [condition]
        if temp is not None:
            parts.append(f"🌡️ {temp}°C")
        if humidity is not None:
            parts.append(f"💧 {humidity}%")
            
        return ", ".join(parts)
        
    # 2. Moon phase
    elif "moon" in entity_lower:
        return MOON_PHASES.get(str(state).lower(), str(state))
        
    # 3. Next sunrise/sunset time
    elif "sun_" in entity_lower or "rising" in entity_lower or "setting" in entity_lower:
        try:
            dt = datetime.fromisoformat(str(state))
            local_dt = dt.astimezone()
            return local_dt.strftime("%H:%M")
        except Exception:
            return str(state)
            
    return str(state)


def build_menu_text(app, title, devices, icon_func=None, extra_func=build_device_extra_text):
    """Универсальный билдер текста для любого меню устройств."""
    if icon_func is None:
        icon_func = lambda state: "🟢" if state == "on" else "⚫"

    if not devices:
        return title

    table = PrettyTable()
    table.field_names = ["Статус", "Устройство", "Активность"]
    table.align = "c"  # center align all columns
    table.set_style(TableStyle.MARKDOWN)

    for name, entity in devices:
        state = app.get_state(entity)
        icon = icon_func(state)
        extra = extra_func(app, name, entity, state) if extra_func else ""
        extra = extra or ""
        table.add_row([icon, name, extra])

    return f"{title}\n```\n{table}\n```"
