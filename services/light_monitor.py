from config import LIGHT_MONITOR_CONFIG, TIMER_CONFIG
from core import devices


class LightMonitor:
    """
    Следит за длительно включенным светом и присылает уведомления с кнопкой выключения.

    Уведомления живут в персистентном хранилище (state.json), поэтому перезагрузка
    модулей или рестарт AppDaemon не оставляет «осиротевших» сообщений в чате:
    при старте и далее по таймеру состояние сверяется с реальным состоянием света.
    """

    def __init__(self, app, telegram_api, store=None):
        self.app = app
        self.telegram = telegram_api
        self.store = store or telegram_api.store

        self.active_timers = {}                  # entity -> handle таймера AppDaemon
        self.pending_group_notifications = {}     # entity -> datetime постановки в очередь
        # message_id (str) -> [entity, ...]; хранится в state.json
        self.notifications = self._load_notifications()
        # Короткие токены групп для callback_data: token (str) -> [entity, ...].
        # Список сущностей в callback_data не влезает в лимит Telegram (64 байта).
        self.groups = self._load_groups()
        # Переопределения таймеров, заданные из Telegram: entity -> minutes | 0 (выключено)
        self.timer_overrides = dict(self.store.get("timers", {}))

        for device in devices.lights():
            self.app.listen_state(self.light_state_changed, device["entity"])

        # Сверка при старте: удалить уведомления для уже погашенного света
        # и запустить таймеры для того, что горит.
        self.reconcile()

    # ───────────── Персистентность уведомлений ─────────────

    def _load_notifications(self):
        raw = self.store.get("notifications", {})
        result = {}
        if isinstance(raw, dict):
            for message_id, entities in raw.items():
                if isinstance(entities, list):
                    result[str(message_id)] = [e for e in entities if isinstance(e, str)]
        return result

    def _load_groups(self):
        raw = self.store.get("notification_groups", {})
        if not isinstance(raw, dict):
            return {}
        return {
            str(token): [e for e in entities if isinstance(e, str)]
            for token, entities in raw.items()
            if isinstance(entities, list)
        }

    def _save_notifications(self):
        self._prune_groups()
        self.store.set("notifications", self.notifications)
        self.store.set("notification_groups", self.groups)

    def _register_group(self, entities):
        """Регистрирует группу и возвращает короткий токен для callback_data."""
        existing = [str(t) for t in self.groups if self.groups[t] == list(entities)]
        if existing:
            return existing[0]
        token = str(max((int(t) for t in self.groups if t.isdigit()), default=0) + 1)
        self.groups[token] = list(entities)
        return token

    def group_entities(self, token):
        """Сущности группового уведомления по токену из callback_data."""
        return list(self.groups.get(str(token), []))

    def _prune_groups(self):
        """Удаляет токены групп, на которые больше не ссылается ни одно уведомление."""
        alive = set()
        for entities in self.notifications.values():
            alive.add(tuple(entities))
        self.groups = {
            token: entities for token, entities in self.groups.items()
            if tuple(entities) in alive
        }

    def _notification_of(self, entity):
        """message_id уведомления, в которое входит сущность, либо None."""
        for message_id, entities in self.notifications.items():
            if entity in entities:
                return message_id
        return None

    # ───────────── Таймеры ─────────────

    def timer_minutes(self, entity):
        """
        Итоговый таймер сущности в минутах.
        None — уведомления отключены (в конфиге не задано или выключено из Telegram).
        """
        if entity in self.timer_overrides:
            value = self.timer_overrides[entity]
            return value if value else None
        device = devices.by_entity(entity)
        if not device:
            return None
        return device.get("timer_minutes")

    def default_timer_minutes(self, entity):
        device = devices.by_entity(entity)
        return device.get("timer_minutes") if device else None

    def set_timer_minutes(self, entity, minutes):
        """
        Устанавливает таймер из Telegram. minutes=0/None выключает уведомления.
        Значение обрезается границами TIMER_CONFIG и сразу применяется к горящему свету.
        """
        if devices.by_entity(entity) is None:
            return None

        if not minutes or int(minutes) <= 0:
            value = 0
        else:
            value = max(TIMER_CONFIG["min_minutes"], min(TIMER_CONFIG["max_minutes"], int(minutes)))

        self.timer_overrides[entity] = value
        self.store.set("timers", self.timer_overrides)
        self.app.log(f"⏱ Timer for {entity} set to {value or 'OFF'} min")

        # Применяем новое значение немедленно
        if value and self.app.get_state(entity) == "on":
            self._start_light_timer(entity)
        else:
            self._cancel_light_timer(entity)
            if not value:
                self._detach_entity(entity)
        return value

    def adjust_timer_minutes(self, entity, delta):
        """Сдвигает таймер на delta минут. Ниже минимума не опускается — для выключения есть set_timer_minutes(0)."""
        current = self.timer_minutes(entity) or self.default_timer_minutes(entity) or TIMER_CONFIG["min_minutes"]
        return self.set_timer_minutes(entity, max(TIMER_CONFIG["min_minutes"], current + delta))

    def reset_timer_minutes(self, entity):
        """Возвращает таймер к значению из config.py."""
        self.timer_overrides.pop(entity, None)
        self.store.set("timers", self.timer_overrides)
        if self.app.get_state(entity) == "on":
            self._start_light_timer(entity)
        return self.timer_minutes(entity)

    def timers_overview(self):
        """[(name, entity, minutes|None, is_on, is_custom)] для меню настроек."""
        overview = []
        for device in devices.lights():
            entity = device["entity"]
            overview.append((
                device["name"],
                entity,
                self.timer_minutes(entity),
                self.app.get_state(entity) == "on",
                entity in self.timer_overrides,
            ))
        return overview

    # ───────────── Реакция на состояние света ─────────────

    def light_state_changed(self, entity, attribute, old, new, kwargs):
        """Обработчик изменения состояния света"""
        if new == "on":
            self._start_light_timer(entity)
        elif new == "off":
            self._cancel_light_timer(entity)
            self._detach_entity(entity)

    def _start_light_timer(self, entity):
        """Запускает таймер уведомления о долгом горении света"""
        self._cancel_light_timer(entity)

        minutes = self.timer_minutes(entity)
        if not minutes:
            return

        handle = self.app.run_in(self._send_light_notification, minutes * 60, entity=entity)
        self.active_timers[entity] = handle
        self.app.log(f"Started timer for {entity}: {minutes} min")

    def _cancel_light_timer(self, entity):
        """Отменяет таймер для света"""
        handle = self.active_timers.pop(entity, None)
        if handle is not None:
            try:
                self.app.cancel_timer(handle)
            except Exception as e:
                self.app.log(f"Failed to cancel timer for {entity}: {e}")
            self.app.log(f"Cancelled timer for {entity}")

    # ───────────── Отправка уведомлений ─────────────

    def _send_light_notification(self, kwargs):
        """Колбэк таймера: отправляет уведомление о долгом горении света"""
        entity = kwargs["entity"]
        self.active_timers.pop(entity, None)

        device = devices.by_entity(entity)
        if not device or self.app.get_state(entity) != "on":
            return

        now = self.app.datetime()
        self.pending_group_notifications[entity] = now

        window_seconds = LIGHT_MONITOR_CONFIG["group_notification_window"] * 60
        # В окно группировки попадают только те, что до сих пор горят
        recent = [
            e for e, ts in list(self.pending_group_notifications.items())
            if (now - ts).total_seconds() <= window_seconds and self.app.get_state(e) == "on"
        ]

        if len(recent) > 1:
            self._send_group_notification(recent)
        else:
            # Запись в pending остаётся до выключения света: если в окне
            # группировки сработает ещё один таймер, уведомления объединятся.
            self._send_individual_notification(entity)

    def _notification_content(self, entities):
        """Текст и клавиатура уведомления для набора сущностей."""
        if len(entities) == 1:
            entity = entities[0]
            minutes = self.timer_minutes(entity) or self.default_timer_minutes(entity)
            text = (f"💡 Свет в {devices.name_of(entity)} горит уже {minutes} минут!"
                    f"\n\nВыключить?")
            keyboard = [[("Выключить", f"/turn_off:{entity}")]]
            return text, keyboard

        names = "\n".join(f"• {devices.name_of(e)}" for e in entities)
        text = f"💡 Свет долго горит в нескольких комнатах:\n{names}\n\nВыключить всё?"
        keyboard = [[("Выключить всё", f"/turn_off_group:{self._register_group(entities)}")]]
        return text, keyboard

    def _send_individual_notification(self, entity):
        """Отправляет индивидуальное уведомление (или обновляет уже существующее)"""
        if self._notification_of(entity):
            return

        text, keyboard = self._notification_content([entity])
        message_id = self.telegram.send_notification(text=text, inline_keyboard=keyboard)
        if message_id:
            self.notifications[str(message_id)] = [entity]
            self._save_notifications()
            self.app.log(f"Sent individual notification for {entity}")

    def _send_group_notification(self, entities):
        """Отправляет групповое уведомление, убирая ранее отправленные по этим сущностям"""
        # Убираем уже висящие уведомления по этим сущностям, чтобы не было дублей
        for entity in entities:
            self._detach_entity(entity, refresh=False)

        text, keyboard = self._notification_content(entities)
        message_id = self.telegram.send_notification(text=text, inline_keyboard=keyboard)
        if message_id:
            self.notifications[str(message_id)] = list(entities)
            self._save_notifications()
            self.app.log(f"Sent group notification for {entities}")
        for entity in entities:
            self.pending_group_notifications.pop(entity, None)

    # ───────────── Снятие уведомлений ─────────────

    def _detach_entity(self, entity, refresh=True):
        """
        Убирает сущность из её уведомления.
        Если в уведомлении больше никого не осталось — удаляет сообщение,
        иначе (refresh=True) переписывает текст под оставшийся свет.
        """
        self.pending_group_notifications.pop(entity, None)

        message_id = self._notification_of(entity)
        if message_id is None:
            return

        remaining = [e for e in self.notifications[message_id] if e != entity]

        if not remaining:
            if self.telegram.delete_notification(int(message_id)):
                del self.notifications[message_id]
                self._save_notifications()
                self.app.log(f"Removed notification for {entity}")
            else:
                # Не удалось удалить — оставляем запись, следующая сверка повторит попытку
                self.notifications[message_id] = []
                self._save_notifications()
            return

        self.notifications[message_id] = remaining
        # Клавиатура строится до сохранения: она регистрирует новый токен группы
        text, keyboard = self._notification_content(remaining)
        self._save_notifications()

        if refresh:
            self.telegram.edit_notification(int(message_id), text, inline_keyboard=keyboard)

    def reconcile(self, kwargs=None):
        """
        Сверяет уведомления и таймеры с реальным состоянием света.

        Вызывается при старте и периодически. Закрывает главную причину
        «висящих» уведомлений: пропущенное событие выключения, рестарт
        AppDaemon или неудачное удаление сообщения.
        """
        # 1. Уведомления по уже выключенному свету
        for message_id in list(self.notifications.keys()):
            entities = self.notifications[message_id]
            still_on = [e for e in entities if self.app.get_state(e) == "on"]

            if still_on == entities and entities:
                continue

            if not still_on:
                if self.telegram.delete_notification(int(message_id)):
                    self.notifications.pop(message_id, None)
                    self.app.log(f"Reconcile: removed stale notification {message_id}")
                continue

            self.notifications[message_id] = still_on
            text, keyboard = self._notification_content(still_on)
            self.telegram.edit_notification(int(message_id), text, inline_keyboard=keyboard)
            self.app.log(f"Reconcile: notification {message_id} narrowed to {still_on}")

        self._save_notifications()

        # 2. Таймеры: должны быть у горящего света без активного уведомления
        for device in devices.lights():
            entity = device["entity"]
            is_on = self.app.get_state(entity) == "on"

            if not is_on:
                self._cancel_light_timer(entity)
                self.pending_group_notifications.pop(entity, None)
                continue

            if not self.timer_minutes(entity):
                self._cancel_light_timer(entity)
                continue

            if entity not in self.active_timers and self._notification_of(entity) is None:
                self.app.log(f"Reconcile: light {entity} is ON without timer, starting it")
                self._start_light_timer(entity)

    # ───────────── Действия по кнопкам уведомлений ─────────────

    def turn_off(self, entity):
        self.app.call_service("homeassistant/turn_off", entity_id=entity)
        self._cancel_light_timer(entity)
        self._detach_entity(entity)

    def turn_off_all(self, entities):
        for entity in entities:
            self.app.call_service("homeassistant/turn_off", entity_id=entity)
            self._cancel_light_timer(entity)
            self._detach_entity(entity, refresh=False)
