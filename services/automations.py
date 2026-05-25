from config import DEVICES
from ui.keyboards import MAIN_KEYBOARD_INLINE

class Automations:
    def __init__(self, app, telegram_api, menu_manager):
        self.app = app
        self.telegram = telegram_api
        self.menu_manager = menu_manager

    def activate_night_mode(self):
        """Активирует ночной режим - выключает свет и закрывает шторы"""
        lights = [d for d in DEVICES if d["type"] == "lights"]
        for device in lights:
            if device["entity"]:
                self.app.call_service("homeassistant/turn_off", entity_id=device["entity"])
        
        blinds = [d for d in DEVICES if d["type"] == "blinds"]
        for device in blinds:
            if device["entity"]:
                self.app.call_service("cover/close_cover", entity_id=device["entity"])
        
        self.menu_manager.current_menu = None
        self.telegram.render_message(
            text="🌙 *Ночной режим активирован*\n\n✅ Свет выключен\n✅ Шторы закрыты",
            inline_keyboard=MAIN_KEYBOARD_INLINE
        )
