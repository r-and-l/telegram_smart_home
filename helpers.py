from datetime import datetime
from prettytable import PrettyTable, TableStyle


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


def build_sensor_extra_text(app, name, entity, state):
    """Возвращает значение сенсора."""
    return str(state) if state is not None else ""


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