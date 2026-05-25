from config import DEVICES, CATEGORIES
from ui.views import build_keyboard, build_menu_text, build_sensor_extra_text
from ui.keyboards import MAIN_KEYBOARD_INLINE

class MenuManager:
    def __init__(self, app, telegram_api):
        self.app = app
        self.telegram = telegram_api
        self.current_menu = None
        self.previous_states = {}

    def show_main_menu(self):
        """Показывает главное меню"""
        self.current_menu = None
        self.telegram.render_message(
            text="🏠 *Умный дом*\n\nВыбери раздел:",
            inline_keyboard=MAIN_KEYBOARD_INLINE
        )

    def show_menu(self, category):
        """Отображает конкретное меню (освещение, климат и т.д.)"""
        self.current_menu = category
        self._initialize_menu_states(category)
        self._render_current_menu()

    def _initialize_menu_states(self, category):
        """Инициализирует словарь состояний для меню"""
        devices = [d for d in DEVICES if d["type"] == category]
        for device in devices:
            if device["entity"]:
                self.previous_states[device["entity"]] = self.app.get_state(device["entity"])

    def auto_update(self, kwargs):
        """Обновляет сообщение только если изменилось состояние устройств 
           или если свет горит (чтобы обновлялся таймер)"""
        if self.current_menu is None or self.telegram.main_message_id is None:
            return
        
        devices = [d for d in DEVICES if d["type"] == self.current_menu]
        
        has_changes = False
        for device in devices:
            if device["entity"]:
                current_state = self.app.get_state(device["entity"])
                previous_state = self.previous_states.get(device["entity"])
                
                # BUGFIX: Force update if state is "on", so the minute timer ticks
                if current_state != previous_state or current_state == "on":
                    self.previous_states[device["entity"]] = current_state
                    has_changes = True
        
        if has_changes:
            self._render_current_menu()

    def _render_current_menu(self):
        category = self.current_menu
        menu = CATEGORIES.get(category)
        if not menu:
            return

        items = [d for d in DEVICES if d["type"] == category]
        devices = [(d["name"], d["entity"]) for d in items if d["entity"]]
        
        if category == "weather":
            # Для погоды показываем простой список сенсоров и их значений
            text = menu["title"].replace("*", "").replace("\n\n", "\n")
            for name, entity in devices:
                state = self.app.get_state(entity)
                value = build_sensor_extra_text(self.app, name, entity, state)
                text += f"{name}: <code>{value}</code>\n"
            buttons = [("⬅️ Назад", "/back")]
            inline_keyboard = build_keyboard(buttons, 2)
            self.telegram.render_message(text=text, inline_keyboard=inline_keyboard, parse_mode="html")
        else:
            text = build_menu_text(self.app, menu["title"], devices)
            buttons = [(name, f"/toggle:{entity}") for name, entity in devices]
            buttons.append(("⬅️ Назад", "/back"))
            inline_keyboard = build_keyboard(buttons, 2)
            self.telegram.render_message(text=text, inline_keyboard=inline_keyboard)
