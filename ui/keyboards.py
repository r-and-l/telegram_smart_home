from config import CATEGORIES
from core import devices
from ui.views import build_keyboard as build_inline_keyboard


def _get_main_menu_keyboard():
    """Создает инлайн клавиатуру для главного меню"""
    buttons = [
        (data.get("button_label"), f"/menu:{category}")
        for category, data in CATEGORIES.items()
        if data.get("button_label")
    ]

    # Прямая кнопка на пульт кондиционера из главного меню
    ac_device = next(
        (d for d in devices.by_type("climate")
         if isinstance(d.get("entity"), str) and d["entity"].startswith("climate.")),
        None
    )
    if ac_device:
        buttons.append(("❄️ Кондей", f"/menu:ac:{ac_device['entity']}"))

    buttons.append(("⏱ Таймеры", "/menu:timers"))
    buttons.append(("🌙 Ночной режим", "/night_mode"))

    return build_inline_keyboard(buttons, per_row=2)


MAIN_KEYBOARD_INLINE = _get_main_menu_keyboard()
