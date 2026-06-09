from config import DEVICES, CATEGORIES
from ui.views import (
    build_keyboard,
    build_menu_text,
    build_sensor_extra_text,
    build_climate_sensors_text,
)
from ui.keyboards import MAIN_KEYBOARD_INLINE

class Menu:
    """Базовый класс для всех меню"""
    def __init__(self, app, category, title):
        self.app = app
        self.category = category
        self.title = title

    def render(self):
        """Возвращает кортеж (text, inline_keyboard, parse_mode)"""
        raise NotImplementedError


class TableMenu(Menu):
    """Стандартное меню с таблицей управляемых устройств и кнопками-переключателями"""
    def render(self):
        items = [d for d in DEVICES if d["type"] == self.category]
        control_devices = [
            (d["name"], d["entity"])
            for d in items
            if d.get("entity") and isinstance(d.get("entity"), str)
        ]
        
        text = build_menu_text(self.app, self.title, control_devices)
        buttons = []
        for name, entity in control_devices:
            if entity.startswith("climate."):
                buttons.append((name, f"/menu:ac:{entity}"))
            else:
                buttons.append((name, f"/toggle:{entity}"))
                
        buttons.append(("⬅️ Назад", "/back"))
        inline_keyboard = build_keyboard(buttons, 3)
        
        return text, inline_keyboard, "markdown"


class ClimateMenu(TableMenu):
    """Климатическое меню с таблицей управления и списком датчиков под ней"""
    def render(self):
        text, inline_keyboard, parse_mode = super().render()
        
        items = [d for d in DEVICES if d["type"] == self.category]
        sensor_items = [d for d in items if d.get("is_sensor")]
        
        text += build_climate_sensors_text(self.app, sensor_items)
        return text, inline_keyboard, parse_mode


class WeatherMenu(Menu):
    """Погодное меню, отображающее список датчиков простым текстом"""
    def render(self):
        items = [d for d in DEVICES if d["type"] == self.category]
        devices = [
            (d["name"], d["entity"])
            for d in items
            if d.get("entity") and isinstance(d.get("entity"), str)
        ]
        
        text = self.title.replace("*", "").replace("\n\n", "\n")
        for name, entity in devices:
            state = self.app.get_state(entity)
            value = build_sensor_extra_text(self.app, name, entity, state)
            text += f"{name}: <code>{value}</code>\n"
            
        buttons = [("⬅️ Назад", "/back")]
        inline_keyboard = build_keyboard(buttons, 2)
        
        return text, inline_keyboard, "html"


class ACMenu(Menu):
    """Меню управления кондиционером"""
    def __init__(self, app, entity_id):
        self.app = app
        self.entity_id = entity_id
        
    def render(self):
        # Находим имя кондиционера в конфиге
        name = "Кондиционер"
        for d in DEVICES:
            if d.get("entity") == self.entity_id:
                name = d.get("name")
                break
                
        state = self.app.get_state(self.entity_id)
        current_temp = self.app.get_state(self.entity_id, attribute="current_temperature")
        target_temp = self.app.get_state(self.entity_id, attribute="temperature")
        fan_mode = self.app.get_state(self.entity_id, attribute="fan_mode")
        
        breather_ent = "fan.xiaomi_mt0_1917_air_fresh"
        breather_state = self.app.get_state(breather_ent)
        breather_mode = self.app.get_state(breather_ent, attribute="preset_mode")
        
        from ui.views import build_ac_text, build_ac_keyboard
        text = build_ac_text(name, state, current_temp, target_temp, fan_mode, breather_state, breather_mode)
        inline_keyboard = build_ac_keyboard(self.entity_id)
        
        return text, inline_keyboard, "markdown"


class MenuManager:
    def __init__(self, app, telegram_api):
        self.app = app
        self.telegram = telegram_api
        self.current_menu = None
        
        # Декларативная регистрация разделов меню
        self.menus = {
            "lights": TableMenu(app, "lights", CATEGORIES["lights"]["title"]),
            "climate": ClimateMenu(app, "climate", CATEGORIES["climate"]["title"]),
            "blinds": TableMenu(app, "blinds", CATEGORIES["blinds"]["title"]),
            "weather": WeatherMenu(app, "weather", CATEGORIES["weather"]["title"]),
        }

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

    def show_ac_menu(self, entity_id):
        """Отображает меню конкретного кондиционера"""
        self.current_menu = f"ac:{entity_id}"
        self._render_current_menu()

    def auto_update(self, kwargs):
        """Обновляет сообщение раз в минуту, если в текущем меню горит свет (для обновления таймеров)"""
        if self.current_menu is None or self.telegram.main_message_id is None:
            return
        
        current_devices = [d for d in DEVICES if d["type"] == self.current_menu]
        has_active_lights = any(
            d.get("type") == "lights" and d.get("entity") and self.app.get_state(d.get("entity")) == "on"
            for d in current_devices
        )
                    
        if has_active_lights:
            self._render_current_menu()

    def _render_current_menu(self):
        """Рендерит текущее открытое меню через соответствующий класс"""
        if self.current_menu.startswith("ac:"):
            entity_id = self.current_menu.replace("ac:", "")
            menu = ACMenu(self.app, entity_id)
        else:
            menu = self.menus.get(self.current_menu)
            
        if not menu:
            return
            
        text, inline_keyboard, parse_mode = menu.render()
        self.telegram.render_message(text=text, inline_keyboard=inline_keyboard, parse_mode=parse_mode)
