# pyrefly: ignore [missing-import]
import appdaemon.plugins.hass.hassapi as hass

from .keyboards import MAIN_KEYBOARD_INLINE
from .menus import show_menu
from .config import DEVICES, NIGHT_MODE

class TelegramSmartHome(hass.Hass):

    def initialize(self):

        self.main_message_id = None
        self.current_menu = None
        self.previous_states = {}  # Словарь для отслеживания предыдущих состояний

        self.listen_event(
            self.telegram_command,
            "telegram_command"
        )

        self.listen_event(
            self.inline_callback,
            "telegram_callback"
        )

        self.run_every(
            self.auto_update,
            "now",
            60
        )

        self.log("SMART HOME BOT STARTED")

    # ==========================================
    # TELEGRAM RENDER MESSAGE
    # ==========================================

    def render_message(self, text, inline_keyboard=None):
        # =====================================
        # FIRST MESSAGE
        # =====================================
        if self.main_message_id is None:

            response = self.call_service(
                "telegram_bot/send_message",
                entity_id="notify.102_info_dom_milyi_dom",
                message=text,
                parse_mode="markdown",
                inline_keyboard=inline_keyboard,
            )

            try:
                self.main_message_id = (
                    response["result"]["response"]["chats"][0]["message_id"]
                )

            except Exception as e:
                self.log(f"ERROR SAVE MESSAGE ID: {e}")
        # =====================================
        # EDIT EXISTING
        # =====================================
        else:
            self.call_service(
                "telegram_bot/edit_message",
                entity_id="notify.102_info_dom_milyi_dom",
                message_id=self.main_message_id,
                message=text,
                parse_mode="markdown",
                inline_keyboard=inline_keyboard
            )

    # ==========================================
    # TELEGRAM СOMMAND (/start)
    # ==========================================

    def telegram_command(self, event_name, data, kwargs):
        command = data.get("command")
        if command == "/start":
            self.main_message_id = None
            self.current_menu = None
            self._show_main_menu()

    # ==========================================
    # SHOW MAIN MENU
    # ==========================================

    def _show_main_menu(self):
        """Показывает главное меню"""
        self.render_message(
            text="🏠 *Умный дом*\n\nВыбери раздел:",
            inline_keyboard=MAIN_KEYBOARD_INLINE
        )

    # ==========================================
    # INLINE BUTTONS
    # ==========================================

    def inline_callback(self, event_name, data, kwargs):
        command = data.get("command", "")
        
        if command.startswith("/menu:"):
            # Навигация в меню раздела
            category = command.replace("/menu:", "")
            self.current_menu = category
            # Инициализируем предыдущие состояния для этого меню
            self._initialize_menu_states(category)
            show_menu(self, category)
        
        elif command.startswith("/toggle:"):
            # Переключение устройства
            entity = command.replace("/toggle:", "")
            self.call_service(
                "homeassistant/toggle",
                entity_id=entity
            )
            # Обновляем текущее меню
            if self.current_menu:
                show_menu(self, self.current_menu)
        
        elif command == "/back":
            # Возврат в главное меню
            self.current_menu = None
            self._show_main_menu()
        
        elif command == "/night_mode":
            # Активация ночного режима
            self._activate_night_mode()
    
    # ==========================================
    # NIGHT MODE
    # ==========================================
    
    def _activate_night_mode(self):
        """Активирует ночной режим - выключает свет и закрывает шторы"""
        # Выключаем все источники света из раздела "lights"
        lights_data = DEVICES.get("lights", {})
        for name, entity in lights_data.get("items", []):
            self.call_service(
                "homeassistant/turn_off",
                entity_id=entity
            )
        
        # Закрываем шторы
        blinds_data = DEVICES.get("blinds", {})
        for name, entity in blinds_data.get("items", []):
            self.call_service(
                "cover/close_cover",
                entity_id=entity
            )
        
        # Меняем меню на сообщение о ночном режиме
        self.current_menu = None
        self.render_message(
            text="🌙 *Ночной режим активирован*\n\n✅ Свет выключен\n✅ Шторы закрыты",
            inline_keyboard=MAIN_KEYBOARD_INLINE
        )
    
    # ==========================================
    # INITIALIZE MENU STATES
    # ==========================================
    
    def _initialize_menu_states(self, category):
        """Инициализирует словарь состояний для меню"""
        menu_data = DEVICES.get(category)
        if menu_data:
            for name, entity in menu_data["items"]:
                self.previous_states[entity] = self.get_state(entity)

    # ==========================================
    # AUTO UPDATE
    # ==========================================

    def auto_update(self, kwargs):
        """Обновляет сообщение только если изменилось состояние устройств"""
        # Если нет текущего меню и нет сообщения, не обновляем
        if self.current_menu is None or self.main_message_id is None:
            return
        
        # Получаем текущий раздел
        menu_data = DEVICES.get(self.current_menu)
        if not menu_data:
            return
        
        # Проверяем, изменилось ли состояние хотя бы одного устройства
        has_changes = False
        for name, entity in menu_data["items"]:
            current_state = self.get_state(entity)
            previous_state = self.previous_states.get(entity)
            
            if current_state != previous_state:
                self.previous_states[entity] = current_state
                has_changes = True
        
        # Если было изменение, обновляем сообщение
        if has_changes:
            show_menu(self, self.current_menu)