from config import DEVICES, CATEGORIES
from ui.views import (
    build_keyboard,
    build_menu_text,
    build_sensor_extra_text,
    build_climate_sensors_text,
)
from ui.keyboards import MAIN_KEYBOARD_INLINE

class MenuManager:
    def __init__(self, app, telegram_api):
        self.app = app
        self.telegram = telegram_api
        self.current_menu = None

        # Регистрация слушателей изменений состояний для всех сущностей в конфиге
        for device in DEVICES:
            for entity in self._get_device_entities(device):
                if entity:
                    self.app.listen_state(self._entity_state_changed, entity)

    def _get_device_entities(self, device):
        """Возвращает список всех сущностей, связанных с устройством"""
        entity_data = device.get("entity")
        if not entity_data:
            return []
        if isinstance(entity_data, str):
            return [entity_data]
        if isinstance(entity_data, list):
            return [e for e in entity_data if isinstance(e, str)]
        if isinstance(entity_data, dict):
            return [e for e in entity_data.values() if isinstance(e, str)]
        return []

    def _entity_state_changed(self, entity, attribute, old, new, kwargs):
        """Обработчик изменения состояния любой отслеживаемой сущности"""
        if self.current_menu is None or self.telegram.main_message_id is None:
            return
            
        # Если изменившаяся сущность входит в текущее меню, перерисовываем его
        current_devices = [d for d in DEVICES if d["type"] == self.current_menu]
        for device in current_devices:
            if entity in self._get_device_entities(device):
                self._render_current_menu()
                break

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
        self._render_current_menu()

    def auto_update(self, kwargs):
        """Обновляет сообщение раз в минуту, если в текущем меню горит свет (для обновления таймеров)"""
        if self.current_menu is None or self.telegram.main_message_id is None:
            return
        
        current_devices = [d for d in DEVICES if d["type"] == self.current_menu]
        has_active_lights = False
        for device in current_devices:
            if device.get("type") == "lights":
                entity = device.get("entity")
                if entity and self.app.get_state(entity) == "on":
                    has_active_lights = True
                    break
                    
        if has_active_lights:
            self._render_current_menu()

    def _render_current_menu(self):
        category = self.current_menu
        menu = CATEGORIES.get(category)
        if not menu:
            return

        items = [d for d in DEVICES if d["type"] == category]
        
        # Разделяем на управляемые устройства и датчики
        control_items = [d for d in items if not d.get("is_sensor")]
        sensor_items = [d for d in items if d.get("is_sensor")]

        if category == "weather":
            # Для погоды показываем простой список сенсоров и их значений
            devices = [(d["name"], d["entity"]) for d in items if d.get("entity")]
            text = menu["title"].replace("*", "").replace("\n\n", "\n")
            for name, entity in devices:
                if isinstance(entity, str):
                    state = self.app.get_state(entity)
                    value = build_sensor_extra_text(self.app, name, entity, state)
                    text += f"{name}: <code>{value}</code>\n"
            buttons = [("⬅️ Назад", "/back")]
            inline_keyboard = build_keyboard(buttons, 2)
            self.telegram.render_message(text=text, inline_keyboard=inline_keyboard, parse_mode="html")
        else:
            control_devices = [
                (d["name"], d["entity"])
                for d in control_items
                if d.get("entity") and isinstance(d.get("entity"), str)
            ]
            text = build_menu_text(self.app, menu["title"], control_devices)
            text += build_climate_sensors_text(self.app, sensor_items)

            buttons = [(name, f"/toggle:{entity}") for name, entity in control_devices]
            buttons.append(("⬅️ Назад", "/back"))
            inline_keyboard = build_keyboard(buttons, 2)
            self.telegram.render_message(text=text, inline_keyboard=inline_keyboard)

