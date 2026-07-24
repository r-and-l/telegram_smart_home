from config import DEVICES, LIGHT_MONITOR_CONFIG

class LightMonitor:
    def __init__(self, app, telegram_api):
        self.app = app
        self.telegram = telegram_api
        
        self.active_timers = {}  # entity -> handle
        self.active_notifications = {}  # entity -> message_id
        self.pending_group_notifications = {}  # entity -> timestamp

        # Слушатели для изменения состояния света
        lights = [d for d in DEVICES if d["type"] == "lights" and d["entity"]]
        for device in lights:
            entity = device["entity"]
            self.app.listen_state(self.light_state_changed, entity)
            # Если свет уже горит при старте бота, запускаем таймер
            if self.app.get_state(entity) == "on":
                self.app.log(f"Light {entity} is already ON on startup, starting timer.")
                self._start_light_timer(entity)

    def light_state_changed(self, entity, attribute, old, new, kwargs):
        """Обработчик изменения состояния света"""
        if new == "on":
            self._start_light_timer(entity)
        elif new == "off":
            self._cancel_light_timer(entity)
            self._remove_light_notification(entity)

    def _start_light_timer(self, entity):
        """Запускает таймер для уведомления о долгом горении света"""
        self._cancel_light_timer(entity)
        
        device = next((d for d in DEVICES if d["entity"] == entity), None)
        if not device or device.get("timer_minutes") is None:
            return
        
        timer_seconds = device["timer_minutes"] * 60
        handle = self.app.run_in(self._send_light_notification, timer_seconds, entity=entity)
        self.active_timers[entity] = handle
        self.app.log(f"Started timer for {entity}: {timer_seconds} seconds")

    def _cancel_light_timer(self, entity):
        """Отменяет таймер для света"""
        if entity in self.active_timers:
            self.app.cancel_timer(self.active_timers[entity])
            del self.active_timers[entity]
            self.app.log(f"Cancelled timer for {entity}")

    def _remove_light_notification(self, entity):
        """Удаляет уведомление о свете"""
        if entity in self.active_notifications:
            message_id = self.active_notifications[entity]
            self.telegram.delete_notification(message_id)
            del self.active_notifications[entity]
            self.app.log(f"Removed notification for {entity}")

    def _send_light_notification(self, kwargs):
        """Отправляет уведомление о долгом горении света"""
        entity = kwargs["entity"]
        device = next((d for d in DEVICES if d["entity"] == entity), None)
        if not device:
            return
        
        if self.app.get_state(entity) != "on":
            return
        
        now = self.app.datetime()
        self.pending_group_notifications[entity] = now
        
        window_seconds = LIGHT_MONITOR_CONFIG["group_notification_window"] * 60
        recent_pending = {
            e: ts for e, ts in self.pending_group_notifications.items()
            if (now - ts).total_seconds() <= window_seconds
        }
        
        if len(recent_pending) > 1:
            self._send_group_notification(recent_pending)
        else:
            self._send_individual_notification(entity, device)

    def _send_individual_notification(self, entity, device):
        """Отправляет индивидуальное уведомление"""
        text = f"💡 Свет в {device['name']} горит уже {device['timer_minutes']} минут!\n\nВыключить?"
        keyboard = [[("Выключить", f"/turn_off:{entity}")]]
        
        message_id = self.telegram.send_notification(text=text, inline_keyboard=keyboard)
        if message_id:
            self.active_notifications[entity] = message_id
            self.app.log(f"Sent individual notification for {entity}")

    def _send_group_notification(self, pending_entities):
        """Отправляет групповое уведомление"""
        entities_list = list(pending_entities.keys())
        names = [next((d["name"] for d in DEVICES if d["entity"] == e), e) for e in entities_list]
        text = f"💡 Несколько светов горят долго:\n" + "\n".join(f"• {name}" for name in names) + "\n\nВыключить все?"
        keyboard = [[("Выключить все", f"/turn_off_all:{','.join(entities_list)}")]]
        
        message_id = self.telegram.send_notification(text=text, inline_keyboard=keyboard)
        if message_id:
            for entity in entities_list:
                self.active_notifications[entity] = message_id
            for entity in entities_list:
                del self.pending_group_notifications[entity]
            self.app.log(f"Sent group notification for {entities_list}")

    def turn_off(self, entity):
        self.app.call_service("homeassistant/turn_off", entity_id=entity)
        self._remove_light_notification(entity)

    def turn_off_all(self, entities):
        for entity in entities:
            self.app.call_service("homeassistant/turn_off", entity_id=entity)
            self._remove_light_notification(entity)
