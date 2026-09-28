"""
Rich HTML builders for Telegram Rich Messages (Bot API 10.1+).

Вместо раздельного text + inline_keyboard все кнопки встраиваются
прямо в тело сообщения через <tg-button> / <tg-button-row>.
"""

from datetime import datetime
from html import escape

from config import TIMER_CONFIG
from core import devices
from ui.translations import WEATHER_TRANSLATIONS, MOON_PHASES, AC_MODES, FAN_MODES


# ───────────── Утилиты ─────────────

def _btn(text, callback_data, style=None):
    """Кнопка с callback_data."""
    style_attr = f' style="{style}"' if style else ''
    return (
        f'<tg-button type="callback_data"{style_attr}'
        f' data="{escape(callback_data)}">{escape(text)}</tg-button>'
    )


def _btn_disabled(text, style=None):
    """Заблокированная кнопка (отображение значения)."""
    style_attr = f' style="{style}"' if style else ''
    return f'<tg-button type="disabled"{style_attr}>{escape(text)}</tg-button>'


def _btn_row(buttons_html, align=None):
    """Оборачивает список HTML-кнопок в <tg-button-row>."""
    align_attr = f' align="{align}"' if align else ''
    return f'<tg-button-row{align_attr}>{"".join(buttons_html)}</tg-button-row>'


def _device_icon(state):
    return "🟢" if state == "on" else "⚫"


def _device_time_on(app, entity, state):
    """Время работы устройства в минутах."""
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


# ───────────── Главное меню ─────────────

def render_main_menu(categories, ac_device=None):
    """Rich HTML для главного меню — таблица-сетка с кнопками в ячейках."""
    buttons = [
        (data.get("button_label"), f"/menu:{category}")
        for category, data in categories.items()
        if data.get("button_label")
    ]
    if ac_device:
        buttons.append(("❄️ Кондей", f"/menu:ac:{ac_device['entity']}"))
    buttons.append(("⏱ Таймеры", "/menu:timers"))
    buttons.append(("🌙 Ночной режим", "/night_mode"))

    # Собираем таблицу по 2 кнопки в ряду
    lines = ["<h3>🏠 Умный дом</h3>", '<table compact>']
    for i in range(0, len(buttons), 2):
        pair = buttons[i:i + 2]
        cells = "".join(
            f'<td align="center">{_btn(text, data)}</td>'
            for text, data in pair
        )
        lines.append(f"<tr>{cells}</tr>")
    lines.append("</table>")

    return "\n".join(lines)


# ───────────── Меню освещения / штор / устройств ─────────────

def render_device_menu(app, title, category, device_list):
    """
    Rich HTML для меню управляемых устройств.
    Каждое устройство — строка с иконкой, названием и кнопкой toggle.
    """
    clean_title = title.replace("*", "").strip()
    lines = [f"<h3>{escape(clean_title)}</h3>"]

    if not device_list:
        lines.append("<p>Нет устройств</p>")
        lines.append(_btn_row([_btn("⬅️ Назад", "/back")], align="center"))
        return "\n".join(lines)

    for name, entity in device_list:
        state = app.get_state(entity)
        icon = _device_icon(state)
        extra = _device_time_on(app, entity, state) or ""

        is_on = state == "on"

        if entity.startswith("climate."):
            action_btn = _btn(f"{icon} {name}", f"/menu:ac:{entity}")
        else:
            style = "success" if is_on else None
            action_btn = _btn(f"{icon} {name}", f"/toggle:{entity}", style=style)

        row_parts = [action_btn]
        if extra:
            row_parts.append(_btn_disabled(extra))

        lines.append(_btn_row(row_parts))

    nav_btns = [_btn("⬅️ Назад", "/back")]
    if category == "lights":
        nav_btns.insert(0, _btn("💤 Выключить все", "/lights_off", "danger"))
    lines.append(_btn_row(nav_btns, align="center"))
    return "\n".join(lines)


# ───────────── Меню климата (устройства + датчики) ─────────────

def render_climate_menu(app, title, device_list, sensor_items):
    """Rich HTML для климатического меню: устройства + таблица датчиков."""
    html = render_device_menu(app, title, "climate", device_list)

    if sensor_items:
        sensor_lines = [
            "<h4>🌡️ Датчики</h4>",
            '<table bordered striped compact>',
            "<tr><th>Датчик</th><th>Температура</th><th>Влажность</th></tr>",
        ]

        for s in sensor_items:
            raw_name = s["name"]
            entity_data = s.get("entity")
            clean_name = raw_name.replace("Т в ", "").replace("Т ", "").strip().capitalize()

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

            elif isinstance(entity_data, list):
                for ent in entity_data:
                    if isinstance(ent, str):
                        val = app.get_state(ent)
                        if val is not None:
                            if "temp" in ent or "temperatura" in ent:
                                temp_str = f"🌡️ {val}°C"
                            elif "vlag" in ent or "vlazhnost" in ent or "hum" in ent:
                                hum_str = f"💧 {val}%"

            elif isinstance(entity_data, str):
                val = app.get_state(entity_data)
                temp_str = str(val) if val is not None else "нет данных"

            sensor_lines.append(
                f"<tr><td>{escape(clean_name)}</td>"
                f"<td align=\"center\">{temp_str}</td>"
                f"<td align=\"center\">{hum_str}</td></tr>"
            )

        sensor_lines.append("</table>")

        # Вставляем датчики перед последней кнопкой "Назад"
        parts = html.rsplit("<tg-button-row", 1)
        html = parts[0] + "\n".join(sensor_lines) + "\n<tg-button-row" + parts[1]

    return html


# ───────────── Погода ─────────────

def render_weather_menu(app, title, device_list):
    """Rich HTML для погодного меню."""
    clean_title = title.replace("*", "").replace("\n\n", "\n").strip()
    lines = [f"<h3>{escape(clean_title)}</h3>"]

    for name, entity in device_list:
        state = app.get_state(entity)
        value = _sensor_value(app, name, entity, state)
        lines.append(f"<p><b>{escape(name)}:</b> {escape(value)}</p>")

    lines.append(_btn_row([_btn("⬅️ Назад", "/back")], align="center"))
    return "\n".join(lines)


def _sensor_value(app, name, entity, state):
    """Форматированное значение сенсора."""
    if state is None:
        return "нет данных"

    entity_lower = entity.lower()

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

    elif "moon" in entity_lower:
        return MOON_PHASES.get(str(state).lower(), str(state))

    elif "sun_" in entity_lower or "rising" in entity_lower or "setting" in entity_lower:
        try:
            dt = datetime.fromisoformat(str(state))
            local_dt = dt.astimezone()
            return local_dt.strftime("%H:%M")
        except Exception:
            return str(state)

    return str(state)


# ───────────── Кондиционер ─────────────

def render_ac_menu(name, state, current_temp, target_temp, fan_mode,
                   entity_id, breather_state=None, breather_mode=None,
                   last_mode=None, sub_menu=None):
    """Rich HTML для пульта кондиционера."""
    is_on = str(state).lower() != "off"

    if is_on:
        mode_text = AC_MODES.get(str(state).lower(), str(state))
        status_icon = "🟢"
    else:
        active_mode = last_mode if last_mode and last_mode != "off" else "cool"
        mode_text = AC_MODES.get(active_mode, AC_MODES["cool"])
        status_icon = "🔴"

    fan_text = FAN_MODES.get(str(fan_mode).lower(), str(fan_mode)) if fan_mode else "—"

    lines = [f"<h3>⚙️ {escape(name)}</h3>"]

    temp_info = ""
    if current_temp is not None:
        temp_info += f" | В комнате: {current_temp}°C"
    lines.append(f"<p>{status_icon} {mode_text}{temp_info}</p>")

    if sub_menu == "modes":
        lines.append("<h4>Выбери режим:</h4>")
        lines.append(_btn_row([
            _btn("❄️ Охлаждение", f"/ac:mode:{entity_id}:cool",
                 "success" if str(state).lower() == "cool" else None),
            _btn("☀️ Обогрев", f"/ac:mode:{entity_id}:heat",
                 "success" if str(state).lower() == "heat" else None),
        ], align="center"))
        lines.append(_btn_row([
            _btn("💧 Осушение", f"/ac:mode:{entity_id}:dry",
                 "success" if str(state).lower() == "dry" else None),
            _btn("💨 Вентилятор", f"/ac:mode:{entity_id}:fan_only",
                 "success" if str(state).lower() == "fan_only" else None),
            _btn("🤖 Авто", f"/ac:mode:{entity_id}:auto",
                 "success" if str(state).lower() == "auto" else None),
        ], align="center"))
        lines.append(_btn_row([
            _btn("⬅️ Назад к кондиционеру", f"/menu:ac:{entity_id}"),
            _btn("🏠 Главная", "/back"),
        ], align="center"))
        return "\n".join(lines)

    if sub_menu == "breather":
        breather_on = breather_state == "on"
        br_mode = str(breather_mode).lower() if breather_mode else ""
        lines.append("<h4>🍃 Бризер</h4>")
        if breather_state:
            br_status = "Вкл" if breather_on else "Выкл"
            br_speed = FAN_MODES.get(br_mode, br_mode)
            lines.append(f"<p>Статус: {br_status} {br_speed}</p>")
        lines.append(_btn_row([
            _btn("🍃 Вкл", f"/ac:breather:{entity_id}:on", "success" if breather_on else None),
            _btn("🛑 Выкл", f"/ac:breather:{entity_id}:off", "danger" if not breather_on else None),
            _btn("🍃 Авт", f"/ac:breather:{entity_id}:auto"),
        ], align="center"))
        lines.append(_btn_row([
            _btn("🍃 1 (Слаб)", f"/ac:breather:{entity_id}:level1",
                 "primary" if br_mode == "level1" else None),
            _btn("🍃 3 (Средн)", f"/ac:breather:{entity_id}:level3",
                 "primary" if br_mode == "level3" else None),
            _btn("🍃 5 (Сильн)", f"/ac:breather:{entity_id}:level5",
                 "primary" if br_mode == "level5" else None),
        ], align="center"))
        lines.append(_btn_row([
            _btn("⬅️ Назад к кондиционеру", f"/menu:ac:{entity_id}"),
            _btn("🏠 Главная", "/back"),
        ], align="center"))
        return "\n".join(lines)

    # Основной пульт
    if target_temp is not None:
        lines.append(_btn_row([
            _btn("🔽 -1°", f"/ac:temp:{entity_id}:down"),
            _btn_disabled(f"🎯 {target_temp}°C"),
            _btn("🔼 +1°", f"/ac:temp:{entity_id}:up"),
        ], align="center"))

    if is_on:
        power_btn = _btn("🛑 Выключить", f"/ac:toggle:{entity_id}:off", "danger")
    else:
        power_btn = _btn("🟢 Включить", f"/ac:toggle:{entity_id}:on", "success")

    lines.append(_btn_row([
        _btn("⚙️ Режимы ▸", f"/menu:ac_modes:{entity_id}"),
        power_btn,
    ], align="center"))

    lines.append(f"<p>Вентилятор: {escape(fan_text)}</p>")
    lines.append(_btn_row([
        _btn("💨 Авт", f"/ac:fan:{entity_id}:auto",
             "primary" if str(fan_mode).lower() == "auto" else None),
        _btn("💨 Слаб", f"/ac:fan:{entity_id}:level1",
             "primary" if str(fan_mode).lower() == "level1" else None),
        _btn("💨 Ср", f"/ac:fan:{entity_id}:level4",
             "primary" if str(fan_mode).lower() == "level4" else None),
        _btn("💨 Сильн", f"/ac:fan:{entity_id}:level7",
             "primary" if str(fan_mode).lower() == "level7" else None),
    ], align="center"))

    lines.append(_btn_row([
        _btn("🍃 Бризер ▸", f"/menu:ac_breather:{entity_id}"),
    ], align="center"))

    lines.append(_btn_row([
        _btn("⬅️ Назад в Климат", "/menu:climate"),
        _btn("🏠 Главная", "/back"),
    ], align="center"))

    return "\n".join(lines)


# ───────────── Таймеры ─────────────

def _timer_value_text(minutes, is_custom):
    if not minutes:
        return "выключен"
    return f"{minutes} мин{' ✏️' if is_custom else ''}"


def render_timers_menu(overview):
    """Rich HTML для списка таймеров света."""
    lines = [
        "<h3>⏱ Таймеры света</h3>",
        "<p>Уведомление приходит, если свет горит дольше таймера. Выбери комнату для настройки.</p>",
    ]

    if not overview:
        lines.append(_btn_row([_btn("⬅️ Назад", "/back")], align="center"))
        return "\n".join(lines)

    for name, entity, minutes, is_on, is_custom in overview:
        icon = "🟢" if is_on else "⚫"
        timer_text = _timer_value_text(minutes, is_custom)
        token = devices.entity_token(entity)
        lines.append(_btn_row([
            _btn(f"{icon} {name} · {timer_text}", f"/timer:open:{token}"),
        ]))

    lines.append(_btn_row([_btn("⬅️ Назад", "/back")], align="center"))
    return "\n".join(lines)


def render_timer_edit_menu(name, entity, minutes, default_minutes, is_on):
    """Rich HTML для экрана настройки таймера одной комнаты."""
    token = devices.entity_token(entity)

    lines = [f"<h3>⏱ Таймер: {escape(name)}</h3>"]

    current_val = "выключен" if not minutes else f"{minutes} мин"
    default_val = "не задан" if not default_minutes else f"{default_minutes} мин"
    light_status = "🟢 горит" if is_on else "⚫ выключен"
    lines.append(f"<p>Текущее значение: <b>{current_val}</b></p>")
    lines.append(f"<p>Из config: {default_val} | Свет: {light_status}</p>")

    step_btns = [
        _btn(f"{'➖' if step < 0 else '➕'} {abs(step)}", f"/timer:adjust:{token}:{step}")
        for step in TIMER_CONFIG["steps"]
    ]
    lines.append(_btn_row(step_btns, align="center"))

    preset_btns = [
        _btn(f"{value} мин", f"/timer:set:{token}:{value}",
             "primary" if minutes == value else None)
        for value in (10, 30, 60, 120)
    ]
    lines.append(_btn_row(preset_btns, align="center"))

    if minutes:
        toggle_btn = _btn("🔕 Отключить", f"/timer:set:{token}:0", "danger")
    else:
        toggle_btn = _btn("🔔 Включить", f"/timer:set:{token}:{default_minutes or 15}", "success")

    lines.append(_btn_row([
        toggle_btn,
        _btn("♻️ По умолчанию", f"/timer:reset:{token}"),
    ], align="center"))

    limits = f"Допустимо {TIMER_CONFIG['min_minutes']}–{TIMER_CONFIG['max_minutes']} мин."
    lines.append(f"<p>{limits}</p>")

    lines.append(_btn_row([
        _btn("⬅️ К таймерам", "/menu:timers"),
        _btn("🏠 Главная", "/back"),
    ], align="center"))

    return "\n".join(lines)
