from config import BREATHER_ENTITY
from core import devices


class Router:
    """
    Маршрутизирует команды и inline-callback'и Telegram.

    Обработчики зарегистрированы декларативно: точные команды в EXACT-таблице,
    префиксные — в PREFIX-таблице (проверяются в порядке убывания длины префикса,
    поэтому "/menu:ac_modes:" находится раньше "/menu:").
    """

    def __init__(self, app, menu_manager, light_monitor, automations, telegram_api, flight_monitor=None):
        self.app = app
        self.menu_manager = menu_manager
        self.light_monitor = light_monitor
        self.automations = automations
        self.telegram = telegram_api
        self.flight_monitor = flight_monitor
        self._current_callback_message_id = None

        self._exact = {
            "/back": lambda: self.menu_manager.show_main_menu(),
            "/night_mode": lambda: self.automations.activate_night_mode(),
            "/lights_off": lambda: self._turn_off_all_lights(),
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
            "/flights:": self._flights,
        }
        # Более длинный (специфичный) префикс должен проверяться первым
        self._prefix = sorted(prefixes.items(), key=lambda kv: -len(kv[0]))

        self.app.listen_event(self.telegram_command, "telegram_command")
        self.app.listen_event(self.inline_callback, "telegram_callback")
        self.app.listen_event(self.telegram_text, "telegram_text")

    # ───────────── Точки входа ─────────────

    def telegram_command(self, event_name, data, kwargs):
        command = data.get("command")
        self.app.log(f"[CMD] RECEIVED COMMAND: {command} (chat: {data.get('chat_id')})")
        self.telegram.update_chat_id(data.get("chat_id"))

        if command == "/start":
            self.telegram.reset_message_id()
            self.menu_manager.show_main_menu()
        elif command in ("/find", "/search") and self.flight_monitor:
            args = data.get("args")
            query = " ".join(args) if isinstance(args, list) else str(args or "")
            if query.strip():
                self.flight_monitor.search_airports(query.strip())
                target = (
                    "flights_origins"
                    if self.menu_manager.current_menu == "flights_origins"
                    else "flights_dest"
                )
                self.menu_manager.show_menu(target)

    def telegram_text(self, event_name, data, kwargs):
        """
        Обработка текстовых сообщений: когда открыто меню авиабилетов (особенно «Откуда» или «Куда»),
        текст (например, «Вьетнам», «Таиланд», «Самара») ищется в базе аэропортов Aviasales.
        """
        text = str(data.get("text") or "").strip()
        if not text or text.startswith("/") or not self.flight_monitor:
            return
        cur = self.menu_manager.current_menu or ""
        if not cur.startswith("flights"):
            return

        self.telegram.update_chat_id(data.get("chat_id"))
        self.app.log(f"[FLIGHTS] Text airport search: {text}")
        self.flight_monitor.search_airports(text)

        # Удаляем сообщение пользователя из чата, чтобы не засорять интерфейс
        user_msg_id = data.get("id") or data.get("message_id")
        if user_msg_id:
            self.telegram.delete_notification(user_msg_id)

        target = "flights_origins" if cur == "flights_origins" else "flights_dest"
        self.menu_manager.show_menu(target)

    def inline_callback(self, event_name, data, kwargs):
        command = data.get("command", "")
        self.app.log(f"[CALLBACK] RECEIVED CALLBACK: {command} (chat: {data.get('chat_id')})")
        self.telegram.update_chat_id(data.get("chat_id"))

        msg_data = data.get("message") if isinstance(data.get("message"), dict) else {}
        self._current_callback_message_id = data.get("message_id") or msg_data.get("message_id")

        try:
            handler = self._exact.get(command)
            if handler:
                handler()
                return

            for prefix, prefix_handler in self._prefix:
                if command.startswith(prefix):
                    prefix_handler(command[len(prefix):])
                    return

            self.app.log(f"[WARN] Unhandled callback: {command}")
        finally:
            self._current_callback_message_id = None

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
            self.app.log(f"[CLIMATE] Turning ON climate {entity} with mode {target_mode}")
            self.app.call_service("climate/set_hvac_mode", entity_id=entity, hvac_mode=target_mode)
        else:
            self.app.log(f"[CLIMATE] Turning OFF climate {entity}")
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

    def _turn_off_all_lights(self):
        """Выключает весь свет из меню освещения."""
        for _name, entity in devices.controllable("lights"):
            if self.app.get_state(entity) == "on":
                self.app.call_service("homeassistant/turn_off", entity_id=entity)
        self.menu_manager.refresh()

    def _turn_off(self, entity):
        self.light_monitor.turn_off(entity, callback_message_id=self._current_callback_message_id)

    def _turn_off_all(self, payload):
        """Совместимость со старыми кнопками, где список сущностей был в callback_data."""
        entities = [e for e in payload.split(",") if e]
        self.light_monitor.turn_off_all(entities, callback_message_id=self._current_callback_message_id)

    def _turn_off_group(self, token):
        """Групповое выключение по короткому токену — список сущностей не влезает в callback_data."""
        entities = self.light_monitor.group_entities(token)
        if not entities:
            self.app.log(f"[WARN] Unknown notification group token: {token}")
            if self._current_callback_message_id:
                self.light_monitor._delete_untracked_callback_message(self._current_callback_message_id)
            return
        self.light_monitor.turn_off_all(entities, callback_message_id=self._current_callback_message_id)

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

    # ───────────── Поиск авиабилетов ─────────────

    def _flights(self, payload):
        """
        Команды меню авиабилетов:
          search               — запустить поиск сейчас и прислать отчёт
          toggle               — включить/выключить ежедневный автопоиск
          time:<delta_min>     — сдвинуть время ежедневной проверки на N минут
          set_time:<HH:MM>     — установить точное время ежедневной проверки
          budget:<delta_rub>   — изменить максимальный бюджет
          origin:<IATA>        — переключить город отправления
          dest:<IATA>          — выбрать город назначения
          from:<delta_days>    — сдвинуть дату начала окна вылета
          to:<delta_days>      — сдвинуть дату конца окна вылета
          span:<days>          — задать ширину окна вылета в днях
          win:<delta_days>     — сдвинуть всё окно вылета
          stay:<min>:<max>     — установить диапазон дней пребывания
          stay_shift:<delta>   — сдвинуть диапазон дней пребывания
          reset                — вернуть настройки по умолчанию
        """
        if not self.flight_monitor:
            return

        if payload == "search":
            # Обновляет таблицу прямо внутри открытого меню без дублирующего сообщения
            self.flight_monitor.run_search(send_report=False, async_run=True)
            self.menu_manager.show_menu("flights")
            return

        if payload == "report":
            # Принудительный поиск с отправкой отдельного сообщения-отчёта
            self.flight_monitor.run_search(send_report=True, async_run=True)
            self.menu_manager.show_menu("flights")
            return

        if payload == "dismiss":
            if self._current_callback_message_id:
                self.telegram.delete_notification(self._current_callback_message_id)
            return

        if payload == "open_menu":
            if self._current_callback_message_id and self._current_callback_message_id != self.telegram.main_message_id:
                self.telegram.delete_notification(self._current_callback_message_id)
            self.telegram.last_text = None
            self.menu_manager.show_menu("flights")
            return

        target_menu = "flights"

        if payload == "toggle":
            self.flight_monitor.toggle_enabled()
        elif payload == "reset":
            self.flight_monitor.reset_settings()
        elif payload.startswith("origin:"):
            code = payload.split(":", 1)[1]
            self.flight_monitor.toggle_origin(code)
            target_menu = "flights_origins"
        elif payload.startswith("dest:"):
            code = payload.split(":", 1)[1]
            self.flight_monitor.toggle_destination(code)
            target_menu = "flights_dest"
        elif payload.startswith("qorig:"):
            query = payload.split(":", 1)[1]
            self.flight_monitor.search_airports(query)
            target_menu = "flights_origins"
        elif payload.startswith("qdest:"):
            query = payload.split(":", 1)[1]
            self.flight_monitor.search_airports(query)
            target_menu = "flights_dest"
        elif payload.startswith("kch:"):
            parts = payload.split(":", 2)
            if len(parts) == 3:
                mode, ch = parts[1], parts[2]
                self.flight_monitor.append_search_char(ch)
                target_menu = "flights_origins" if mode == "orig" else "flights_dest"
        elif payload.startswith("kbs:"):
            mode = payload.split(":", 1)[1]
            self.flight_monitor.backspace_search_char()
            target_menu = "flights_origins" if mode == "orig" else "flights_dest"
        elif payload.startswith("kclr:"):
            mode = payload.split(":", 1)[1]
            self.flight_monitor.clear_airport_search()
            target_menu = "flights_origins" if mode == "orig" else "flights_dest"
        elif payload.startswith("one_way:"):
            val = payload.split(":", 1)[1]
            self.flight_monitor.set_one_way(val in ("1", "true", "True"))
            target_menu = "flights"
        elif payload.startswith("one_way_dates:"):
            val = payload.split(":", 1)[1]
            self.flight_monitor.set_one_way(val in ("1", "true", "True"))
            target_menu = "flights_dates"
        elif payload.startswith("cal_nav:"):
            try:
                delta_m = int(payload.split(":", 1)[1])
                self.flight_monitor.shift_calendar_month(delta_m)
            except ValueError:
                return
            target_menu = "flights_dates"
        elif payload.startswith("cal_day:"):
            iso_d = payload.split(":", 1)[1]
            self.flight_monitor.pick_calendar_date(iso_d)
            target_menu = "flights_dates"
        elif payload == "cal_whole":
            self.flight_monitor.select_whole_calendar_month()
            target_menu = "flights_dates"
        elif payload.startswith("transfers:"):
            try:
                tr = int(payload.split(":", 1)[1])
                self.flight_monitor.set_max_transfers(tr)
            except ValueError:
                return
        elif payload.startswith("duration:"):
            try:
                hrs = int(payload.split(":", 1)[1])
                self.flight_monitor.set_max_duration(hrs)
            except ValueError:
                return
        elif payload.startswith("from:"):
            try:
                delta = int(payload.split(":", 1)[1])
                self.flight_monitor.shift_depart_from(delta)
            except ValueError:
                return
            target_menu = "flights_dates"
        elif payload.startswith("to:"):
            try:
                delta = int(payload.split(":", 1)[1])
                self.flight_monitor.shift_depart_to(delta)
            except ValueError:
                return
            target_menu = "flights_dates"
        elif payload.startswith("span:"):
            try:
                span = int(payload.split(":", 1)[1])
                self.flight_monitor.set_window_span(span)
            except ValueError:
                return
            target_menu = "flights_dates"
        elif payload.startswith("win:"):
            try:
                delta = int(payload.split(":", 1)[1])
                self.flight_monitor.shift_window(delta)
            except ValueError:
                return
            target_menu = "flights_dates"
        elif payload.startswith("stay:"):
            parts = payload.split(":")
            if len(parts) == 3:
                try:
                    self.flight_monitor.set_stay_range(int(parts[1]), int(parts[2]))
                except ValueError:
                    return
            target_menu = "flights_dates"
        elif payload.startswith("stay_shift:"):
            try:
                delta = int(payload.split(":", 1)[1])
                self.flight_monitor.shift_stay_range(delta)
            except ValueError:
                return
            target_menu = "flights_dates"
        elif payload.startswith("time:"):
            try:
                delta = int(payload.split(":", 1)[1])
                self.flight_monitor.adjust_check_time(delta)
            except ValueError:
                return
        elif payload.startswith("set_time:"):
            hh_mm = payload.split(":", 1)[1]
            self.flight_monitor.set_check_time(hh_mm)
        elif payload.startswith("budget:"):
            try:
                delta_rub = int(payload.split(":", 1)[1])
                self.flight_monitor.adjust_max_price(delta_rub)
            except ValueError:
                return
        else:
            return

        self.menu_manager.show_menu(target_menu)

