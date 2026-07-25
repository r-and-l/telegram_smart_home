
from datetime import datetime
from ui.translations import WEATHER_TRANSLATIONS, MOON_PHASES


def build_rich_table_block(headers, rows, is_bordered=True, is_striped=True):
    """
    Строит блок InputRichBlockTable для Telegram sendRichMessage API.
    Возвращает dict (один блок) для массива blocks.
    """
    cells = []
    # Заголовки
    if headers:
        header_row = [{"text": h, "is_header": True} for h in headers]
        cells.append(header_row)
    # Данные
    for row in rows:
        data_row = [{"text": str(cell) if cell else ""} for cell in row]
        cells.append(data_row)

    return {
        "type": "table",
        "is_bordered": is_bordered,
        "is_striped": is_striped,
        "cells": cells
    }


def build_rich_paragraph(text):
    """Строит блок InputRichBlockParagraph для Telegram sendRichMessage API."""
    return {"type": "paragraph", "text": text}


def build_rich_section_heading(text):
    """Строит блок InputRichBlockSectionHeading для Telegram sendRichMessage API."""
    return {"type": "section_heading", "text": text}


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


def build_menu_rich_blocks(app, title, devices, icon_func=None, extra_func=build_device_extra_text):
    """
    Строит список rich-блоков для меню устройств (заголовок + таблица).
    Возвращает (blocks, fallback_text).
    """
    if icon_func is None:
        icon_func = lambda state: "🟢" if state == "on" else "⚫"

    clean_title = title.replace("*", "").strip()

    if not devices:
        blocks = [build_rich_section_heading(clean_title)]
        return blocks, clean_title

    headers = ["", "Устройство", "Активность"]
    rows = []

    for name, entity in devices:
        state = app.get_state(entity)
        icon = icon_func(state)
        extra = extra_func(app, name, entity, state) if extra_func else ""
        extra = extra or ""
        rows.append([icon, name, extra])

    blocks = [
        build_rich_section_heading(clean_title),
        build_rich_table_block(headers, rows)
    ]
    
    # Fallback текст для случая когда Rich API недоступен
    fallback_lines = [f"<b>{clean_title}</b>\n"]
    for row in rows:
        fallback_lines.append(f"{row[0]} {row[1]}  {row[2]}")
    fallback_text = "\n".join(fallback_lines)
    
    return blocks, fallback_text


def build_climate_sensors_text(app, sensor_items):
    """Строит текстовый блок для датчиков климата."""
    if not sensor_items:
        return ""
        
    sensor_text = "\n\n"
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
            sensor_text += f"<b>{name}</b>: {val_str}\n"
            
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
            sensor_text += f"<b>{name}</b>: {val_str}\n"
            
        elif isinstance(entity_data, str):
            val = app.get_state(entity_data)
            val_str = str(val) if val is not None else "нет данных"
            sensor_text += f"<b>{name}</b>: {val_str}\n"
            
    return sensor_text

def build_ac_text(name, state, current_temp, target_temp, fan_mode, breather_state=None, breather_mode=None):
    """Строит текст для подменю кондиционера"""
    modes_ru = {
        "off": "🛑 Выключен",
        "cool": "❄️ Охлаждение",
        "heat": "☀️ Обогрев",
        "dry": "💧 Осушение",
        "fan_only": "💨 Вентилятор",
        "auto": "🤖 Авто"
    }
    fan_modes_ru = {
        "auto": "Авто",
        "low": "Низкая",
        "medium": "Средняя",
        "high": "Высокая",
        "silent": "Тихий",
        "turbo": "Турбо",
        "level1": "Скорость 1 (Мин)",
        "level2": "Скорость 2",
        "level3": "Скорость 3",
        "level4": "Скорость 4 (Средн)",
        "level5": "Скорость 5",
        "level6": "Скорость 6",
        "level7": "Скорость 7 (Макс)",
    }
    
    mode_text = modes_ru.get(str(state).lower(), str(state))
    fan_text = fan_modes_ru.get(str(fan_mode).lower(), str(fan_mode)) if fan_mode else "нет данных"
    
    text = f"⚙️ <b>Управление: {name}</b>\n\n"
    text += f"<b>Режим:</b> {mode_text}\n"
    if current_temp is not None:
        text += f"<b>В комнате:</b> {current_temp}°C\n"
    if target_temp is not None:
        text += f"<b>Установлено:</b> {target_temp}°C\n"
    text += f"<b>Вентилятор:</b> {fan_text}\n"
    
    if breather_state:
        b_state_ru = "Вкл" if breather_state == "on" else "Выкл"
        b_mode_ru = fan_modes_ru.get(str(breather_mode).lower(), str(breather_mode)) if breather_mode else ""
        text += f"<b>Бризер:</b> {b_state_ru} {b_mode_ru}\n"
        
    return text

def build_ac_rich_blocks(name, state, current_temp, target_temp, fan_mode, breather_state=None, breather_mode=None):
    """Строит rich-блоки для подменю кондиционера"""
    modes_ru = {
        "off": "🛑 Выключен",
        "cool": "❄️ Охлаждение",
        "heat": "☀️ Обогрев",
        "dry": "💧 Осушение",
        "fan_only": "💨 Вентилятор",
        "auto": "🤖 Авто"
    }
    fan_modes_ru = {
        "auto": "Авто",
        "low": "Низкая",
        "medium": "Средняя",
        "high": "Высокая",
        "silent": "Тихий",
        "turbo": "Турбо",
        "level1": "Скорость 1 (Мин)",
        "level2": "Скорость 2",
        "level3": "Скорость 3",
        "level4": "Скорость 4 (Средн)",
        "level5": "Скорость 5",
        "level6": "Скорость 6",
        "level7": "Скорость 7 (Макс)",
    }
    
    mode_text = modes_ru.get(str(state).lower(), str(state))
    fan_text = fan_modes_ru.get(str(fan_mode).lower(), str(fan_mode)) if fan_mode else "нет данных"
    
    rows = [
        ["Режим", mode_text],
    ]
    if current_temp is not None:
        rows.append(["В комнате", f"{current_temp}°C"])
    if target_temp is not None:
        rows.append(["Установлено", f"{target_temp}°C"])
    rows.append(["Вентилятор", fan_text])
    
    if breather_state:
        b_state_ru = "Вкл" if breather_state == "on" else "Выкл"
        b_mode_ru = fan_modes_ru.get(str(breather_mode).lower(), str(breather_mode)) if breather_mode else ""
        rows.append(["Бризер", f"{b_state_ru} {b_mode_ru}".strip()])
    
    return [
        build_rich_section_heading(f"⚙️ Управление: {name}"),
        build_rich_table_block(["Параметр", "Значение"], rows, is_bordered=True, is_striped=True)
    ]


def build_ac_keyboard(entity_id):
    """Строит клавиатуру для пульта кондиционера"""
    return [
        [
            ("❄️ Охл", f"/ac:mode:{entity_id}:cool"),
            ("☀️ Нагрев", f"/ac:mode:{entity_id}:heat"),
            ("💨 Вент", f"/ac:mode:{entity_id}:fan_only"),
        ],
        [
            ("💧 Осуш", f"/ac:mode:{entity_id}:dry"),
            ("🛑 Выкл", f"/ac:mode:{entity_id}:off"),
        ],
        [
            ("➖ Меньше", f"/ac:temp:{entity_id}:down"),
            ("➕ Больше", f"/ac:temp:{entity_id}:up"),
        ],
        [
            ("Авт", f"/ac:fan:{entity_id}:auto"),
            ("Слаб", f"/ac:fan:{entity_id}:level1"),
            ("Ср", f"/ac:fan:{entity_id}:level4"),
            ("Сильн", f"/ac:fan:{entity_id}:level7"),
        ],
        [
            ("🍃 Выкл", f"/ac:breather:{entity_id}:off"),
            ("🍃 Авт", f"/ac:breather:{entity_id}:auto"),
            ("🍃 1", f"/ac:breather:{entity_id}:level1"),
            ("🍃 3", f"/ac:breather:{entity_id}:level3"),
            ("🍃 5", f"/ac:breather:{entity_id}:level5"),
        ],
        [
            ("⬅️ Назад в Климат", "/menu:climate")
        ]
    ]
