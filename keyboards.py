from .config import CATEGORIES as DEVICES
from .helpers import build_keyboard as build_inline_keyboard


def _get_main_menu_keyboard():
    """Создает инлайн клавиатуру для главного меню"""
    buttons = [
        (data.get("button_label"), f"/menu:{category}")
        for category, data in DEVICES.items()
        if data.get("button_label")
    ]
    # Добавляем кнопку ночного режима
    buttons.append(("🌙 Ночной режим", "/night_mode"))
    
    return build_inline_keyboard(buttons, per_row=2)


MAIN_KEYBOARD_INLINE = _get_main_menu_keyboard()
