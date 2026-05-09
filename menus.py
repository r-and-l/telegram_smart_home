from .config import DEVICES
from .helpers import build_keyboard
from .rooms import build_rooms_text

class Menu:
    def __init__(self, app, category):
        self.app = app
        self.category = category
        self.devices = DEVICES.get(category, [])

    def get_text(self):
        raise NotImplementedError

    def get_buttons(self):
        return [(name, f"/toggle:{entity}") for name, entity in self.devices]

    def show(self):
        text = self.get_text()
        buttons = self.get_buttons()
        inline_keyboard = build_keyboard(buttons, 3)
        self.app.render_message(text=text, inline_keyboard=inline_keyboard)

class LightsMenu(Menu):
    def __init__(self, app):
        super().__init__(app, "lights")

    def get_text(self):
        return build_rooms_text(self.app, self.devices)

class ClimateMenu(Menu):
    def __init__(self, app):
        super().__init__(app, "climate")

    def get_text(self):
        text = "🌬 *Климат*\n\n"
        for name, entity in self.devices:
            state = self.app.get_state(entity)
            icon = "🟢" if state == "on" else "⚫"
            text += f"{icon} {name}\n"
        return text

    def get_buttons(self):
        return [(name, f"/toggle:{entity}") for name, entity in self.devices]

# Factory for menus
def get_menu(app, category):
    menus = {
        "lights": LightsMenu,
        "climate": ClimateMenu,
    }
    menu_class = menus.get(category)
    if menu_class:
        return menu_class(app)
    return None
