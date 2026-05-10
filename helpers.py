from datetime import datetime
from tabulate import tabulate


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


def build_menu_text(app, title, devices, icon_func=None, extra_func=build_device_extra_text):
    """Универсальный билдер текста для любого меню устройств."""
    if icon_func is None:
        icon_func = lambda state: "🟢" if state == "on" else "⚫"

    if not devices:
        return title

    rows = []
    for name, entity in devices:
        state = app.get_state(entity)
        icon = icon_func(state)
        extra = extra_func(app, name, entity, state) if extra_func else None
        rows.append((icon, name, extra or ""))

    headers = ["Статус", "Устройство", "Активность"]
    table = tabulate(rows, headers=headers, tablefmt="github")
    return f"{title}```\n{table}\n```"