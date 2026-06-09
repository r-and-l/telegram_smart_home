from datetime import datetime
from prettytable import PrettyTable, TableStyle
from ui.translations import WEATHER_TRANSLATIONS, MOON_PHASES

def build_keyboard(items, per_row=3):
    """Строит инлайн-клавиатуру с заданным числом кнопок в ряду."""
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


def build_sensor_extra_text(app, name, entity, state):
    """Возвращает форматированное значение сенсора на русском языке."""
    if state is None:
        return "нет данных"
        
    entity_lower = entity.lower()
    
    # 1. Погода weather.*
    if entity_lower.startswith("weather."):
        condition = WEATHER_TRANSLATIONS.get(str(state).lower(), str(state))
        temp = app.get_state(entity, attribute="temperature")
        humidity = app.get_state(entity, attribute="humidity")
        
        parts = [condition]
        if temp is not None:
            parts.append(f"🌡️ {temp}°C")
        if humidity is not None:
            parts.append(f"💧 {humidity}%")
            
        return ", ".join(parts)
        
    # 2. Фаза луны
    elif "moon" in entity_lower:
        return MOON_PHASES.get(str(state).lower(), str(state))
        
    # 3. Время восхода/заката
    elif "sun_" in entity_lower or "rising" in entity_lower or "setting" in entity_lower:
        try:
            dt = datetime.fromisoformat(str(state))
            local_dt = dt.astimezone()
            return local_dt.strftime("%H:%M")
        except Exception:
            return str(state)
            
    return str(state)


def build_menu_text(app, title, devices, icon_func=None, extra_func=build_device_extra_text):
    """Универсальный билдер текста для любого меню устройств (в виде Markdown-таблицы)."""
    if icon_func is None:
        icon_func = lambda state: "🟢" if state == "on" else "⚫"

    if not devices:
        return title

    table = PrettyTable()
    table.field_names = ["Статус", "Устройство", "Активность"]
    table.align = "c"
    table.set_style(TableStyle.MARKDOWN)

    for name, entity in devices:
        state = app.get_state(entity)
        icon = icon_func(state)
        extra = extra_func(app, name, entity, state) if extra_func else ""
        extra = extra or ""
        table.add_row([icon, name, extra])

    return f"{title}\n```{table}\n```"


def build_climate_sensors_text(app, sensor_items):
    """Строит текстовый блок для датчиков климата."""
    if not sensor_items:
        return ""
        
    sensor_text = "\n"
    for s in sensor_items:
        name = s["name"]
        entity_data = s.get("entity")
        
        if isinstance(entity_data, dict):
            temp_entity = entity_data.get("temperature")
            hum_entity = entity_data.get("humidity")
            
            temp_val = app.get_state(temp_entity) if temp_entity else None
            hum_val = app.get_state(hum_entity) if hum_entity else None
            
            parts = []
            if temp_val is not None:
                parts.append(f"🌡️ {temp_val}°C")
            if hum_val is not None:
                parts.append(f"💧 {hum_val}%")
            val_str = " | ".join(parts) if parts else "нет данных"
            sensor_text += f"**{name}**: {val_str}\n"
            
        elif isinstance(entity_data, list):
            vals = []
            for ent in entity_data:
                if isinstance(ent, str):
                    val = app.get_state(ent)
                    if val is not None:
                        if "temp" in ent or "temperatura" in ent:
                            vals.append(f"🌡️ {val}°C")
                        elif "vlag" in ent or "vlazhnost" in ent or "hum" in ent:
                            vals.append(f"💧 {val}%")
                        else:
                            vals.append(str(val))
            val_str = " | ".join(vals) if vals else "нет данных"
            sensor_text += f"{name}: {val_str}\n"
            
        elif isinstance(entity_data, str):
            val = app.get_state(entity_data)
            val_str = str(val) if val is not None else "нет данных"
            sensor_text += f"{name}: {val_str}\n"
            
    return sensor_text

def build_ac_text(name, state, current_temp, target_temp):
    """Строит текст для подменю кондиционера"""
    modes_ru = {
        "off": "🛑 Выключен",
        "cool": "❄️ Охлаждение",
        "heat": "☀️ Обогрев",
        "dry": "💧 Осушение",
        "fan_only": "💨 Вентилятор",
        "auto": "🤖 Авто",
        "fresh_air": "🍃 Бризер"
    }
    mode_text = modes_ru.get(str(state).lower(), str(state))
    
    text = f"⚙️ **Управление: {name}**\n\n"
    text += f"**Режим:** {mode_text}\n"
    if current_temp is not None:
        text += f"**В комнате:** {current_temp}°C\n"
    if target_temp is not None:
        text += f"**Установлено:** {target_temp}°C\n"
        
    return text

def build_ac_keyboard(entity_id):
    """Строит клавиатуру для пульта кондиционера"""
    return [
        [
            ("❄️ Охл", f"/ac:mode:{entity_id}:cool"),
            ("☀️ Наг", f"/ac:mode:{entity_id}:heat"),
        ],
        [
            ("💨 Вент", f"/ac:mode:{entity_id}:fan_only"),
            ("💧 Осуш", f"/ac:mode:{entity_id}:dry"),
        ],
        [
            ("🛑 Выкл", f"/ac:mode:{entity_id}:off"),
            ("🍃 Бризер", f"/ac:mode:{entity_id}:fresh_air"),
        ],
        [
            ("➖ Меньше", f"/ac:temp:{entity_id}:down"),
            ("➕ Больше", f"/ac:temp:{entity_id}:up"),
        ],
        [
            ("⬅️ Назад в Климат", "/menu:climate")
        ]
    ]
