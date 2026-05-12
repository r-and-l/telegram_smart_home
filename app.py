# pyrefly: ignore [missing-import]
import appdaemon.plugins.hass.hassapi as hass

from .keyboards import MAIN_KEYBOARD_INLINE
from .menus import show_menu
from .config import DEVICES, LIGHT_MONITOR_CONFIG

class TelegramSmartHome(hass.Hass):

    def initialize(self):

        self.main_message_id = None
        self.current_menu = None
        self.previous_states = {}  # Словарь для отслеживания предыдущих состояний

        # Мониторинг света
        self.active_timers = {}  # entity -> handle
        self.active_notifications = {}  # entity -> message_id
        self.pending_group_notifications = {}  # entity -> timestamp для групповых уведомлений

        self.listen_event(
            self.telegram_command,
            "telegram_command"
        )

        self.listen_event(
            self.inline_callback,
            "telegram_callback"
        )

        # Слушатели для изменения состояния света
        lights = [d for d in DEVICES if d["type"] == "lights" and d["entity"]]
        for device in lights:
            self.listen_state(self.light_state_changed, device["entity"])

        self.run_every(
            self.auto_update,
            "now",
            60
        )

        self.log("SMART HOME BOT STARTED")

    # ==========================================
    # LIGHT STATE CHANGED
    # ==========================================

    def light_state_changed(self, entity, attribute, old, new, kwargs):
        """Обработчик изменения состояния света"""
        if new == "on":
            # Свет включился - запускаем таймер
            self._start_light_timer(entity)
        elif new == "off":
            # Свет выключился - отменяем таймер и удаляем уведомление
            self._cancel_light_timer(entity)
            self._remove_light_notification(entity)

    # ==========================================
    # LIGHT TIMER METHODS
    # ==========================================

    def _start_light_timer(self, entity):
        """Запускает таймер для уведомления о долгом горении света"""
        # Отменяем существующий таймер, если есть
        self._cancel_light_timer(entity)
        
        # Находим устройство
        device = next((d for d in DEVICES if d["entity"] == entity), None)
        if not device or device.get("timer_minutes") is None:
            return
        
        timer_seconds = device["timer_minutes"] * 60
        handle = self.run_in(self._send_light_notification, timer_seconds, entity=entity)
        self.active_timers[entity] = handle
        self.log(f"Started timer for {entity}: {timer_seconds} seconds")

    def _cancel_light_timer(self, entity):
        """Отменяет таймер для света"""
        if entity in self.active_timers:
            self.cancel_timer(self.active_timers[entity])
            del self.active_timers[entity]
            self.log(f"Cancelled timer for {entity}")

    def _remove_light_notification(self, entity):
        """Удаляет уведомление о свете"""
        if entity in self.active_notifications:
            message_id = self.active_notifications[entity]
            # Редактируем сообщение на пустое для удаления
            self.call_service(
                "telegram_bot/edit_message",
                entity_id=LIGHT_MONITOR_CONFIG["notification_entity"],
                message_id=message_id,
                message="",
                inline_keyboard=[]
            )
            del self.active_notifications[entity]
            self.log(f"Removed notification for {entity}")

    def _send_light_notification(self, kwargs):
        """Отправляет уведомление о долгом горении света"""
        entity = kwargs["entity"]
        device = next((d for d in DEVICES if d["entity"] == entity), None)
        if not device:
            return
        
        # Проверяем, включен ли еще свет
        if self.get_state(entity) != "on":
            return
        
        # Добавляем в pending для групповых уведомлений
        now = self.datetime()
        self.pending_group_notifications[entity] = now
        
        # Проверяем, есть ли другие pending в окне
        window_seconds = LIGHT_MONITOR_CONFIG["group_notification_window"] * 60
        recent_pending = {
            e: ts for e, ts in self.pending_group_notifications.items()
            if (now - ts).total_seconds() <= window_seconds
        }
        
        if len(recent_pending) > 1:
            # Групповое уведомление
            self._send_group_notification(recent_pending)
        else:
            # Индивидуальное уведомление
            self._send_individual_notification(entity, device)

    def _send_individual_notification(self, entity, device):
        """Отправляет индивидуальное уведомление"""
        text = f"💡 Свет в {device['name']} горит уже {device['timer_minutes']} минут!\n\nВыключить?"
        keyboard = [[("Выключить", f"/turn_off:{entity}")]]
        
        response = self.call_service(
            "telegram_bot/send_message",
            entity_id=LIGHT_MONITOR_CONFIG["notification_entity"],
            message=text,
            inline_keyboard=keyboard
        )
        
        if response and "result" in response:
            message_id = response["result"]["response"]["chats"][0]["message_id"]
            self.active_notifications[entity] = message_id
            self.log(f"Sent individual notification for {entity}")

    def _send_group_notification(self, pending_entities):
        """Отправляет групповое уведомление"""
        entities_list = list(pending_entities.keys())
        names = [next((d["name"] for d in DEVICES if d["entity"] == e), e) for e in entities_list]
        text = f"💡 Несколько светов горят долго:\n" + "\n".join(f"• {name}" for name in names) + "\n\nВыключить все?"
        keyboard = [[("Выключить все", f"/turn_off_all:{','.join(entities_list)}")]]
        
        response = self.call_service(
            "telegram_bot/send_message",
            entity_id=LIGHT_MONITOR_CONFIG["notification_entity"],
            message=text,
            inline_keyboard=keyboard
        )
        
        if response and "result" in response:
            message_id = response["result"]["response"]["chats"][0]["message_id"]
            # Сохраняем для каждого
            for entity in entities_list:
                self.active_notifications[entity] = message_id
            # Очищаем pending
            for entity in entities_list:
                del self.pending_group_notifications[entity]
            self.log(f"Sent group notification for {entities_list}")

    # ==========================================
    # TELEGRAM RENDER MESSAGE
    # ==========================================

    def render_message(self, text, inline_keyboard=None, parse_mode="markdown"):
        # =====================================
        # FIRST MESSAGE
        # =====================================
        if self.main_message_id is None:

            response = self.call_service(
                "telegram_bot/send_message",
                entity_id="notify.102_info_dom_milyi_dom",
                message=text,
                parse_mode=parse_mode,
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
                parse_mode=parse_mode,
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
        
        elif command.startswith("/turn_off:"):
            # Выключение света из уведомления
            entity = command.replace("/turn_off:", "")
            self.call_service(
                "homeassistant/turn_off",
                entity_id=entity
            )
            # Удаляем уведомление
            self._remove_light_notification(entity)
        
        elif command.startswith("/turn_off_all:"):
            # Выключение всех светов из группового уведомления
            entities = command.replace("/turn_off_all:", "").split(",")
            for entity in entities:
                self.call_service(
                    "homeassistant/turn_off",
                    entity_id=entity
                )
                self._remove_light_notification(entity)
        
        elif command == "/night_mode":
            # Активация ночного режима
            self._activate_night_mode()
    
    # ==========================================
    # NIGHT MODE
    # ==========================================
    
    def _activate_night_mode(self):
        """Активирует ночной режим - выключает свет и закрывает шторы"""
        # Выключаем все источники света из раздела "lights"
        lights = [d for d in DEVICES if d["type"] == "lights"]
        for device in lights:
            if device["entity"]:
                self.call_service(
                    "homeassistant/turn_off",
                    entity_id=device["entity"]
                )
        
        # Закрываем шторы
        blinds = [d for d in DEVICES if d["type"] == "blinds"]
        for device in blinds:
            if device["entity"]:
                self.call_service(
                    "cover/close_cover",
                    entity_id=device["entity"]
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
        devices = [d for d in DEVICES if d["type"] == category]
        for device in devices:
            if device["entity"]:
                self.previous_states[device["entity"]] = self.get_state(device["entity"])

    # ==========================================
    # AUTO UPDATE
    # ==========================================

    def auto_update(self, kwargs):
        """Обновляет сообщение только если изменилось состояние устройств"""
        # Если нет текущего меню и нет сообщения, не обновляем
        if self.current_menu is None or self.main_message_id is None:
            return
        
        # Получаем текущий раздел
        devices = [d for d in DEVICES if d["type"] == self.current_menu]
        
        # Проверяем, изменилось ли состояние хотя бы одного устройства
        has_changes = False
        for device in devices:
            if device["entity"]:
                current_state = self.get_state(device["entity"])
                previous_state = self.previous_states.get(device["entity"])
                
                if current_state != previous_state:
                    self.previous_states[device["entity"]] = current_state
                    has_changes = True
        
        # Если было изменение, обновляем сообщение
        if has_changes:
            show_menu(self, self.current_menu)