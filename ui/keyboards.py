from config import CATEGORIES, DEVICES
from ui.views import build_keyboard as build_inline_keyboard

def _get_main_menu_keyboard():
    """Создает инлайн клавиатуру для главного меню"""
    buttons = [
        (data.get("button_label"), f"/menu:{category}")
        for category, data in CATEGORIES.items()
        if data.get("button_label")
    ]
    
    # Ищем кондиционер для прямой кнопки из главного меню
    ac_device = next((d for d in DEVICES if d.get("type") == "climate" and isinstance(d.get("entity"), str) and d.get("entity").startswith("climate.")), None)
    if ac_device:
        buttons.append(("❄️ Кондей", f"/menu:ac:{ac_device['entity']}"))

    # Добавляем кнопку ночного режима
    buttons.append(("🌙 Ночной режим", "/night_mode"))
    
    return build_inline_keyboard(buttons, per_row=2)


MAIN_KEYBOARD_INLINE = _get_main_menu_keyboard()
