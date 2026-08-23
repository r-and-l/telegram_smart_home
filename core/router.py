from config import BREATHER_ENTITY
from core import devices


class Router:
    """
    Маршрутизирует команды и inline-callback'и Telegram.

    Обработчики зарегистрированы декларативно: точные команды в EXACT-таблице,
    префиксные — в PREFIX-таблице (проверяются в порядке убывания длины префикса,
    поэтому "/menu:ac_modes:" находится раньше "/menu:").
    """

    def __init__(self, app, menu_manager, light_monitor, automations, telegram_api):
        self.app = app
        self.menu_manager = menu_manager
        self.light_monitor = light_monitor
        self.automations = automations
        self.telegram = telegram_api

        self._exact = {
            "/back": lambda: self.menu_manager.show_main_menu(),
            "/night_mode": lambda: self.automations.activate_night_mode(),
        }

        prefixes = {
            "/menu:ac_modes:": self._open_ac_modes,
            "/menu:ac_breather:": self._open_ac_breather,
            "/menu:ac:": self._open_ac,
            "/menu:": self._open_menu,
            "/ac:toggle:": self._ac_toggle,
            "/ac:mode:": self._ac_mode,
            "/ac:temp:": self._ac_temp,
            "/ac:fan:": self._ac_fan,
            "/ac:breather:": self._ac_breather,
            "/toggle:": self._toggle_entity,
            "/turn_off_group:": self._turn_off_group,
            "/turn_off_all:": self._turn_off_all,
            "/turn_off:": self._turn_off,
            "/timer:": self._timer,
        }
        # Более длинный (специфичный) префикс должен проверяться первым
        self._prefix = sorted(prefixes.items(), key=lambda kv: -len(kv[0]))

        self.app.listen_event(self.telegram_command, "telegram_command")
        self.app.listen_event(self.inline_callback, "telegram_callback")

    # ───────────── Точки входа ─────────────

    def telegram_command(self, event_name, data, kwargs):
        command = data.get("command")
        self.app.log(f"📥 RECEIVED COMMAND: {command} (chat: {data.get('chat_id')})")
        self.telegram.update_chat_id(data.get("chat_id"))

        if command == "/start":
            self.telegram.reset_message_id()
            self.menu_manager.show_main_menu()

    def inline_callback(self, event_name, data, kwargs):
        command = data.get("command", "")
        self.app.log(f"🔘 RECEIVED CALLBACK: {command} (chat: {data.get('chat_id')})")
        self.telegram.update_chat_id(data.get("chat_id"))

        handler = self._exact.get(command)
        if handler:
            handler()
            return

        for prefix, prefix_handler in self._prefix:
            if command.startswith(prefix):
                prefix_handler(command[len(prefix):])
                return

        self.app.log(f"⚠️ Unhandled callback: {command}")

    # ───────────── Навигация по меню ─────────────

    def _open_menu(self, category):
        self.menu_manager.show_menu(category)

    def _open_ac(self, entity):
        self.menu_manager.show_ac_menu(entity)

    def _open_ac_modes(self, entity):
        self.menu_manager.show_ac_modes_menu(entity)

    def _open_ac_breather(self, entity):
        self.menu_manager.show_ac_breather_menu(entity)

    # ───────────── Кондиционер ─────────────

    def _ac_args(self, payload, expected=2):
        """Разбирает хвост команды вида 'climate.entity:value'."""
        parts = payload.split(":")
        return parts if len(parts) == expected else None

    def _ac_toggle(self, payload):
        # climate.entity_id:on|off
        args = self._ac_args(payload)
        if not args:
            return
        entity, action = args
        if action == "on":
            target_mode = self.app.last_ac_modes.get(entity, "cool")
            self.app.log(f"🟢 Turning ON climate {entity} with mode {target_mode}")
            self.app.call_service("climate/set_hvac_mode", entity_id=entity, hvac_mode=target_mode)
        else:
            self.app.log(f"🛑 Turning OFF climate {entity}")
            self.app.call_service("climate/turn_off", entity_id=entity)
        self.menu_manager.refresh()

    def _ac_mode(self, payload):
        # climate.entity_id:cool
        args = self._ac_args(payload)
        if not args:
            return
        entity, mode = args

        if mode != "off":
            self.app.last_ac_modes[entity] = mode

        if mode == "fresh_air":
            self.app.call_service("climate/set_preset_mode", entity_id=entity, preset_mode="fresh_air")
        elif mode == "off":
            self.app.call_service("climate/turn_off", entity_id=entity)
        else:
            self.app.call_service("climate/set_hvac_mode", entity_id=entity, hvac_mode=mode)
        self.menu_manager.refresh()

    def _ac_temp(self, payload):
        # climate.entity_id:up|down
        args = self._ac_args(payload)
        if not args:
            return
        entity, direction = args
        current_temp = self.app.get_state(entity, attribute="temperature")
        if current_temp is not None:
            try:
                new_temp = float(current_temp) + (1.0 if direction == "up" else -1.0)
                self.app.call_service("climate/set_temperature", entity_id=entity, temperature=new_temp)
            except (TypeError, ValueError):
                pass
        self.menu_manager.show_ac_menu(entity)

    def _ac_fan(self, payload):
        # climate.entity_id:low
        args = self._ac_args(payload)
        if not args:
            return
        entity, fan_mode = args
        self.app.call_service("climate/set_fan_mode", entity_id=entity, fan_mode=fan_mode)
        self.menu_manager.show_ac_menu(entity)

    def _ac_breather(self, payload):
        # climate.entity_id:level1
        args = self._ac_args(payload)
        if not args:
            return
        _entity, mode = args
        if mode == "off":
            self.app.call_service("fan/turn_off", entity_id=BREATHER_ENTITY)
        else:
            self.app.call_service("fan/turn_on", entity_id=BREATHER_ENTITY)
            if mode != "on":
                self.app.call_service("fan/set_preset_mode", entity_id=BREATHER_ENTITY, preset_mode=mode)
        self.menu_manager.refresh()

    # ───────────── Свет и уведомления ─────────────

    def _toggle_entity(self, entity):
        self.app.call_service("homeassistant/toggle", entity_id=entity)
        self.menu_manager.refresh()

    def _turn_off(self, entity):
        self.light_monitor.turn_off(entity)

    def _turn_off_all(self, payload):
        """Совместимость со старыми кнопками, где список сущностей был в callback_data."""
        entities = [e for e in payload.split(",") if e]
        self.light_monitor.turn_off_all(entities)

    def _turn_off_group(self, token):
        """Групповое выключение по короткому токену — список сущностей не влезает в callback_data."""
        entities = self.light_monitor.group_entities(token)
        if not entities:
            self.app.log(f"⚠️ Unknown notification group token: {token}")
            return
        self.light_monitor.turn_off_all(entities)

    # ───────────── Таймеры уведомлений ─────────────

    def _timer(self, payload):
        """
        Команды настройки таймеров (entity передаётся коротким токеном):
          open:<token>            — экран настройки
          set:<token>:<minutes>   — точное значение (0 — отключить уведомления)
          adjust:<token>:<delta>  — сдвиг на N минут
          reset:<token>           — вернуть значение из config.py
        """
        parts = payload.split(":")
        action, token = parts[0], parts[1] if len(parts) > 1 else None
        if not token:
            return
        entity = devices.entity_by_token(token)

        if action == "open":
            self.menu_manager.show_timer_edit_menu(entity)
            return

        if action == "reset":
            self.light_monitor.reset_timer_minutes(entity)
        elif action in ("set", "adjust") and len(parts) > 2:
            try:
                value = int(parts[2])
            except ValueError:
                return
            if action == "set":
                self.light_monitor.set_timer_minutes(entity, value)
            else:
                self.light_monitor.adjust_timer_minutes(entity, value)
        else:
            return

        self.menu_manager.show_timer_edit_menu(entity)
