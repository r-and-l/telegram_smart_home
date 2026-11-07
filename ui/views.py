
from datetime import datetime
from config import TIMER_CONFIG
from core import devices
from ui.translations import WEATHER_TRANSLATIONS, MOON_PHASES, AC_MODES, FAN_MODES


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
    """Строит заголовок как блок paragraph для Telegram sendRichMessage API."""
    return {"type": "paragraph", "text": text}



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


def build_climate_sensors_rich_blocks(app, sensor_items):
    """
    Строит таблицу rich-блоков для датчиков климата.
    Возвращает (table_block, fallback_text).
    """
    if not sensor_items:
        return None, ""

    headers = ["Датчик", "Температура", "Влажность"]
    rows = []
    fallback_lines = ["\nДатчики:"]

    for s in sensor_items:
        raw_name = s["name"]
        entity_data = s.get("entity")

        clean_name = raw_name.replace("Т в ", "").replace("Т ", "").strip().capitalize()
        if "туалет" in clean_name.lower() and "🚽" not in clean_name:
            clean_name = f"🚽 {clean_name}"
        elif "ванн" in clean_name.lower() and "🛁" not in clean_name:
            clean_name = f"🛁 {clean_name}"

        temp_str = "—"
        hum_str = "—"

        if isinstance(entity_data, dict):
            temp_entity = entity_data.get("temperature")
            hum_entity = entity_data.get("humidity")

            temp_val = app.get_state(temp_entity) if temp_entity else None
            hum_val = app.get_state(hum_entity) if hum_entity else None

            if temp_val is not None:
                temp_str = f"🌡️ {temp_val}°C"
            if hum_val is not None:
                hum_str = f"💧 {hum_val}%"

            rows.append([clean_name, temp_str, hum_str])
            fallback_lines.append(f"• {clean_name}: {temp_str} | {hum_str}")

        elif isinstance(entity_data, list):
            vals = []
            for ent in entity_data:
                if isinstance(ent, str):
                    val = app.get_state(ent)
                    if val is not None:
                        if "temp" in ent or "temperatura" in ent:
                            temp_str = f"🌡️ {val}°C"
                        elif "vlag" in ent or "vlazhnost" in ent or "hum" in ent:
                            hum_str = f"💧 {val}%"
                        else:
                            vals.append(str(val))
            if vals:
                rows.append([clean_name, ", ".join(vals), "—"])
            else:
                rows.append([clean_name, temp_str, hum_str])
            fallback_lines.append(f"• {clean_name}: {temp_str} | {hum_str}")

        elif isinstance(entity_data, str):
            val = app.get_state(entity_data)
            val_str = str(val) if val is not None else "нет данных"
            rows.append([clean_name, val_str, "—"])
            fallback_lines.append(f"• {clean_name}: {val_str}")

    table_block = build_rich_table_block(headers, rows, is_bordered=True, is_striped=True)
    fallback_text = "\n".join(fallback_lines)

    return table_block, fallback_text


def _ac_summary(state, current_temp, target_temp, fan_mode, breather_state=None,
                breather_mode=None, last_mode=None):
    """
    Готовит пары (подпись, значение) для меню кондиционера.
    Используется и текстовым, и табличным рендерером.
    """
    is_on = str(state).lower() != "off"
    status_text = "🟢 Включен" if is_on else "🔴 Выключен"

    if is_on:
        mode_text = AC_MODES.get(str(state).lower(), str(state))
    else:
        active_mode = last_mode if last_mode and last_mode != "off" else "cool"
        mode_text = AC_MODES.get(active_mode, AC_MODES["cool"])

    fan_text = FAN_MODES.get(str(fan_mode).lower(), str(fan_mode)) if fan_mode else "нет данных"

    rows = [("Статус", status_text), ("Режим", mode_text)]
    if current_temp is not None:
        rows.append(("В комнате", f"{current_temp}°C"))
    if target_temp is not None:
        rows.append(("Установлено", f"{target_temp}°C"))
    rows.append(("Вентилятор", fan_text))

    if breather_state:
        breather_status = "Вкл" if breather_state == "on" else "Выкл"
        breather_speed = FAN_MODES.get(str(breather_mode).lower(), str(breather_mode)) if breather_mode else ""
        rows.append(("Бризер", f"{breather_status} {breather_speed}".strip()))

    return rows


def build_ac_text(name, state, current_temp, target_temp, fan_mode, breather_state=None, breather_mode=None, last_mode=None):
    """Строит текст для подменю кондиционера"""
    rows = _ac_summary(state, current_temp, target_temp, fan_mode, breather_state, breather_mode, last_mode)
    lines = [f"⚙️ <b>Управление: {name}</b>\n"]
    lines += [f"<b>{label}:</b> {value}" for label, value in rows]
    return "\n".join(lines) + "\n"


def build_ac_rich_blocks(name, state, current_temp, target_temp, fan_mode, breather_state=None, breather_mode=None, last_mode=None):
    """Строит rich-блоки для подменю кондиционера"""
    rows = _ac_summary(state, current_temp, target_temp, fan_mode, breather_state, breather_mode, last_mode)
    return [
        build_rich_section_heading(f"⚙️ Управление: {name}"),
        build_rich_table_block(["Параметр", "Значение"], [list(r) for r in rows],
                               is_bordered=True, is_striped=True)
    ]


# ───────────── Настройка таймеров света ─────────────

def _timer_value_text(minutes, is_custom):
    if not minutes:
        return "выключен"
    return f"{minutes} мин{' ✏️' if is_custom else ''}"


def build_timers_rich_blocks(overview):
    """
    Строит таблицу таймеров света.
    overview: [(name, entity, minutes|None, is_on, is_custom)].
    Возвращает (blocks, fallback_text).
    """
    heading = "⏱ Таймеры света"
    hint = "Уведомление приходит, если свет горит дольше таймера. Выбери комнату для настройки."

    if not overview:
        blocks = [build_rich_section_heading(heading), build_rich_paragraph(hint)]
        return blocks, f"<b>{heading}</b>\n\n{hint}"

    rows = [
        ["🟢" if is_on else "⚫", name, _timer_value_text(minutes, is_custom)]
        for name, _entity, minutes, is_on, is_custom in overview
    ]

    blocks = [
        build_rich_section_heading(heading),
        build_rich_table_block(["", "Комната", "Таймер"], rows),
        build_rich_paragraph(hint),
    ]

    fallback_lines = [f"<b>{heading}</b>\n"]
    fallback_lines += [f"{row[0]} {row[1]}  {row[2]}" for row in rows]
    fallback_lines.append(f"\n{hint}")
    return blocks, "\n".join(fallback_lines)


def build_timers_keyboard(overview, per_row=2):
    """Кнопки выбора комнаты для настройки таймера."""
    buttons = [
        (f"{name} · {_timer_value_text(minutes, is_custom)}", f"/timer:open:{devices.entity_token(entity)}")
        for name, entity, minutes, _is_on, is_custom in overview
    ]
    keyboard = build_keyboard(buttons, per_row)
    keyboard.append([("⬅️ Назад", "/back")])
    return keyboard


def build_timer_edit_rich_blocks(name, minutes, default_minutes, is_on):
    """Экран настройки таймера одной комнаты. Возвращает (blocks, fallback_text)."""
    heading = f"⏱ Таймер: {name}"
    rows = [
        ["Текущее значение", "выключен" if not minutes else f"{minutes} мин"],
        ["Из config.py", "не задан" if not default_minutes else f"{default_minutes} мин"],
        ["Свет сейчас", "🟢 горит" if is_on else "⚫ выключен"],
    ]
    limits = f"Допустимо {TIMER_CONFIG['min_minutes']}–{TIMER_CONFIG['max_minutes']} мин."

    blocks = [
        build_rich_section_heading(heading),
        build_rich_table_block(["Параметр", "Значение"], rows),
        build_rich_paragraph(limits),
    ]

    fallback_lines = [f"<b>{heading}</b>\n"]
    fallback_lines += [f"<b>{row[0]}:</b> {row[1]}" for row in rows]
    fallback_lines.append(f"\n{limits}")
    return blocks, "\n".join(fallback_lines)


def build_timer_edit_keyboard(entity, minutes, default_minutes=None):
    """Кнопки правки таймера: шаги из TIMER_CONFIG, пресеты, сброс и выключение."""
    token = devices.entity_token(entity)

    step_row = [
        (f"{'➖' if step < 0 else '➕'} {abs(step)}", f"/timer:adjust:{token}:{step}")
        for step in TIMER_CONFIG["steps"]
    ]

    preset_row = [
        (f"{value} мин", f"/timer:set:{token}:{value}")
        for value in (10, 30, 60, 120)
    ]

    if minutes:
        toggle_btn = ("🔕 Отключить", f"/timer:set:{token}:0")
    else:
        # Включаем со значением из config.py, а при его отсутствии — с 15 минутами
        toggle_btn = ("🔔 Включить", f"/timer:set:{token}:{default_minutes or 15}")

    return [
        step_row,
        preset_row,
        [toggle_btn, ("♻️ По умолчанию", f"/timer:reset:{token}")],
        [("⬅️ К таймерам", "/menu:timers"), ("🏠 Главная", "/back")],
    ]


def build_ac_keyboard(entity_id, sub_menu=None, state="off"):
    """Строит клавиатуру для пульта кондиционера (основную, режимов или подменю бризера)"""
    if sub_menu == "modes":
        return [
            [
                ("❄️ Охлаждение", f"/ac:mode:{entity_id}:cool"),
                ("☀️ Обогрев", f"/ac:mode:{entity_id}:heat"),
            ],
            [
                ("💧 Осушение", f"/ac:mode:{entity_id}:dry"),
                ("💨 Вентилятор", f"/ac:mode:{entity_id}:fan_only"),
                ("🤖 Авто", f"/ac:mode:{entity_id}:auto"),
            ],
            [
                ("⬅️ Назад к кондиционеру", f"/menu:ac:{entity_id}"),
                ("🏠 Главная", "/back"),
            ]
        ]

    if sub_menu == "breather":
        return [
            [
                ("🍃 Вкл", f"/ac:breather:{entity_id}:on"),
                ("🛑 Выкл", f"/ac:breather:{entity_id}:off"),
                ("🍃 Авт", f"/ac:breather:{entity_id}:auto"),
            ],
            [
                ("🍃 1 (Слаб)", f"/ac:breather:{entity_id}:level1"),
                ("🍃 3 (Средн)", f"/ac:breather:{entity_id}:level3"),
                ("🍃 5 (Сильн)", f"/ac:breather:{entity_id}:level5"),
            ],
            [
                ("⬅️ Назад к кондиционеру", f"/menu:ac:{entity_id}"),
                ("🏠 Главная", "/back"),
            ]
        ]

    # Динамическая кнопка вкл/выкл в зависимости от статуса кондиционера
    if str(state).lower() == "off":
        power_btn = ("🟢 Включить", f"/ac:toggle:{entity_id}:on")
    else:
        power_btn = ("🛑 Выключить", f"/ac:toggle:{entity_id}:off")

    return [
        [
            ("⚙️ Режимы ▸", f"/menu:ac_modes:{entity_id}"),
            power_btn,
        ],
        [
            ("➖ Меньше", f"/ac:temp:{entity_id}:down"),
            ("➕ Больше", f"/ac:temp:{entity_id}:up"),
        ],
        [
            ("💨 Авт", f"/ac:fan:{entity_id}:auto"),
            ("💨 Слаб", f"/ac:fan:{entity_id}:level1"),
            ("💨 Ср", f"/ac:fan:{entity_id}:level4"),
            ("💨 Сильн", f"/ac:fan:{entity_id}:level7"),
        ],
        [
            ("🍃 Бризер ▸", f"/menu:ac_breather:{entity_id}"),
        ],
        [
            ("⬅️ Назад в Климат", "/menu:climate"),
            ("🏠 Главная", "/back"),
        ]
    ]


# ───────────── Авиабилеты (Flight Finder) ─────────────

def build_flights_rich_blocks(summary):
    """Строит rich-блоки и fallback-текст для меню поиска авиабилетов."""
    origins_str = ", ".join(summary["origins"])
    dests = summary.get("destinations") or [summary["destination"]]
    dests_str = ", ".join(dests)
    enabled = summary["enabled"]
    check_time = summary["check_time"]
    price_fmt = f"{summary['max_price']:,}".replace(",", " ")

    heading = f"✈️ Авиабилеты: {origins_str} → {dests_str}"
    schedule_str = f"🟢 Вкл (ежедневно в {check_time})" if enabled else "🔴 Выключен"

    param_rows = [
        ["Откуда", ", ".join(summary.get("origins_labels", summary["origins"]))],
        ["Куда", summary.get("destination_label", dests_str)],
        ["Окно вылета", f"{summary['depart_from']} — {summary['depart_to']}"],
        ["Длительность", f"{summary['stay_min_days']}–{summary['stay_max_days']} дн."],
        ["Бюджет", f"до {price_fmt} ₽"],
        ["Автопоиск", schedule_str],
    ]
    if summary.get("last_check"):
        param_rows.append(["Последняя проверка", f"{summary['last_check']} (найдено: {summary['last_total']})"])

    blocks = [
        build_rich_section_heading(heading),
        build_rich_table_block(["Параметр", "Значение"], param_rows),
    ]

    fallback_lines = [f"<b>{heading}</b>\n"]
    for k, v in param_rows:
        fallback_lines.append(f"<b>{k}:</b> {v}")

    if not summary.get("has_token"):
        warn = "⚠️ Не задан tp_token в FLIGHT_CONFIG (config.py) или TP_TOKEN."
        blocks.append(build_rich_paragraph(warn))
        fallback_lines.append(f"\n{warn}")
    elif summary.get("last_error"):
        err = f"⚠️ Ошибка: {summary['last_error']}"
        blocks.append(build_rich_paragraph(err))
        fallback_lines.append(f"\n{err}")

    results = summary.get("last_results") or []
    if results:
        flight_rows = []
        fallback_lines.append("\n<b>Лучшие варианты:</b>")
        for r in results:
            r_price = f"{int(r['price']):,} ₽".replace(",", " ")
            r_dest = r.get("destination", dests[0])
            route = f"{r['origin']}→{r_dest}"
            airline = str(r.get("airline") or "—")
            dep_str = str(r["depart"])[:16]
            ret_str = str(r["return"])[:16]
            info = f"{r['stay_days']}д, пер.{r['transfers_to']}/{r['transfers_back']}"
            flight_rows.append([r_price, route, airline, dep_str, ret_str, info])
            fallback_lines.append(f"• {r_price} | {route} ({airline}) | {dep_str} – {ret_str} ({info})")
        blocks.append(
            build_rich_table_block(["Цена", "Рейс", "А/к", "Туда", "Обратно", "Инфо"], flight_rows)
        )

    return blocks, "\n".join(fallback_lines)


def build_flights_keyboard(summary, sub_menu=None):
    """Инлайн-клавиатура для меню поиска авиабилетов (основная и подменю)."""
    origins = summary["origins"]
    origins_str = ", ".join(origins)
    dests = summary.get("destinations") or [summary["destination"]]
    dests_str = ", ".join(dests)

    if sub_menu == "origins":
        kb = [
            [
                ("🇷🇺 Россия", "/flights:qorig:Россия"),
                ("🇰🇿 Казахстан", "/flights:qorig:Казахстан"),
                ("🇧🇾 Беларусь", "/flights:qorig:Беларусь"),
            ]
        ]
        for item in summary.get("place_search_results") or []:
            code = item["code"]
            label = item.get("label") or item.get("name") or code
            kb.append([(f"{'🟢' if code in origins else '➕'} {label} ({code})", f"/flights:origin:{code}")])
        items = [
            (f"{'🟢' if code in origins else '⚫'} {city} ({code})", f"/flights:origin:{code}")
            for code, city in summary.get("origin_options", {}).items()
        ]
        kb.extend(build_keyboard(items, per_row=2))
        kb.append([("⬅️ К билетам", "/menu:flights"), ("🏠 Главная", "/back")])
        return kb

    if sub_menu == "dest":
        kb = [
            [
                ("🇻🇳 Вьетнам", "/flights:qdest:Вьетнам"),
                ("🇹🇭 Таиланд", "/flights:qdest:Таиланд"),
                ("🇹🇷 Турция", "/flights:qdest:Турция"),
                ("🇮🇩 Индонезия", "/flights:qdest:Индонезия"),
            ],
            [
                ("🇨🇳 Китай", "/flights:qdest:Китай"),
                ("🇦🇪 ОАЭ", "/flights:qdest:ОАЭ"),
                ("🇱🇰 Шри-Ланка", "/flights:qdest:Шри-Ланка"),
                ("🇲🇾 Малайзия", "/flights:qdest:Малайзия"),
            ],
        ]
        for item in summary.get("place_search_results") or []:
            code = item["code"]
            label = item.get("label") or item.get("name") or code
            kb.append([(f"{'🟢' if code in dests else '➕'} {label} ({code})", f"/flights:dest:{code}")])
        items = [
            (f"{'🟢' if code in dests else '⚫'} {city} ({code})", f"/flights:dest:{code}")
            for code, city in summary.get("destination_options", {}).items()
        ]
        kb.extend(build_keyboard(items, per_row=2))
        kb.append([("⬅️ К билетам", "/menu:flights"), ("🏠 Главная", "/back")])
        return kb

    if sub_menu == "dates":
        return [
            [
                ("⏪ От -30д", "/flights:from:-30"),
                ("◀️ От -7д", "/flights:from:-7"),
                ("-1д", "/flights:from:-1"),
                ("+1д", "/flights:from:1"),
                ("▶️ От +7д", "/flights:from:7"),
                ("⏩ От +30д", "/flights:from:30"),
            ],
            [
                ("◀️ До -7д", "/flights:to:-7"),
                ("До -1д", "/flights:to:-1"),
                ("До +1д", "/flights:to:1"),
                ("▶️ До +7д", "/flights:to:7"),
            ],
            [
                ("Окно 7д", "/flights:span:7"),
                ("Окно 11д", "/flights:span:11"),
                ("Окно 14д", "/flights:span:14"),
                ("Окно 30д", "/flights:span:30"),
            ],
            [
                ("⏪ Окно -1м", "/flights:win:-30"),
                ("◀️ Окно -7д", "/flights:win:-7"),
                ("▶️ Окно +7д", "/flights:win:7"),
                ("⏩ Окно +1м", "/flights:win:30"),
            ],
            [
                ("Дней -5", "/flights:stay_shift:-5"),
                ("Дней -1", "/flights:stay_shift:-1"),
                ("Дней +1", "/flights:stay_shift:1"),
                ("Дней +5", "/flights:stay_shift:5"),
            ],
            [
                ("7–10 дн", "/flights:stay:7:10"),
                ("12–16 дн", "/flights:stay:12:16"),
                ("20–25 дн", "/flights:stay:20:25"),
                ("27–33 дн", "/flights:stay:27:33"),
            ],
            [("⬅️ К билетам", "/menu:flights"), ("🏠 Главная", "/back")],
        ]

    enabled = summary["enabled"]
    search_label = "⏳ Поиск..." if summary.get("is_searching") else "🔍 Найти сейчас"
    toggle_btn = (
        ("🔕 Выкл автопоиск", "/flights:toggle")
        if enabled
        else ("🔔 Вкл автопоиск", "/flights:toggle")
    )
    return [
        [(search_label, "/flights:search")],
        [
            ("🔄 Туда-обратно", "/flights:one_way:0"),
            ("➡️ В одну сторону", "/flights:one_way:1"),
        ],
        [
            (f"🛫 Откуда ({origins_str}) ▸", "/menu:flights_origins"),
            (f"🛬 Куда ({dests_str}) ▸", "/menu:flights_dest"),
        ],
        [
            (f"📅 Даты ({summary['depart_from']} .. {summary['depart_to']}) ▸", "/menu:flights_dates"),
        ],
        [
            ("Прямые", "/flights:transfers:0"),
            ("≤ 1 пер.", "/flights:transfers:1"),
            ("≤ 2 пер.", "/flights:transfers:2"),
            ("≤ 3 пер.", "/flights:transfers:3"),
        ],
        [
            ("≤ 24 ч", "/flights:duration:24"),
            ("≤ 36 ч", "/flights:duration:36"),
            ("≤ 48 ч", "/flights:duration:48"),
        ],
        [
            ("➖ 1ч", "/flights:time:-60"),
            ("➖ 15м", "/flights:time:-15"),
            ("➕ 15м", "/flights:time:15"),
            ("➕ 1ч", "/flights:time:60"),
        ],
        [
            ("08:00", "/flights:set_time:08:00"),
            ("10:00", "/flights:set_time:10:00"),
            ("14:00", "/flights:set_time:14:00"),
            ("20:00", "/flights:set_time:20:00"),
        ],
        [
            ("➖ 5 000 ₽", "/flights:budget:-5000"),
            ("➕ 5 000 ₽", "/flights:budget:5000"),
        ],
        [toggle_btn, ("♻️ По умолчанию", "/flights:reset")],
        [("⬅️ Назад", "/back")],
    ]


