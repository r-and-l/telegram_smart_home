from .config import DEVICES, CATEGORIES
from .helpers import build_keyboard, build_menu_text


def show_menu(app, category):
    menu = CATEGORIES.get(category)
    if not menu:
        return

    items = [d for d in DEVICES if d["type"] == category]
    devices = [(d["name"], d["entity"]) for d in items if d["entity"]]
    
    text = build_menu_text(app, menu["title"], devices)
    buttons = [(name, f"/toggle:{entity}") for name, entity in devices]
    
    # Добавляем кнопку "Назад" в конец
    buttons.append(("⬅️ Назад", "/back"))
    
    inline_keyboard = build_keyboard(buttons, 2)
    app.render_message(text=text, inline_keyboard=inline_keyboard)
