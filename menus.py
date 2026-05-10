from .config import DEVICES
from .helpers import build_keyboard, build_menu_text


def show_menu(app, category):
    menu = DEVICES.get(category)
    if not menu:
        return

    text = build_menu_text(app, menu["title"], menu["items"])
    buttons = [(name, f"/toggle:{entity}") for name, entity in menu["items"]]
    
    # Добавляем кнопку "Назад" в конец
    buttons.append(("⬅️ Назад", "/back"))
    
    inline_keyboard = build_keyboard(buttons, 2)
    app.render_message(text=text, inline_keyboard=inline_keyboard)
