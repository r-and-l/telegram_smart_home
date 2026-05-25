import logging
from config import LIGHT_MONITOR_CONFIG

class TelegramAPI:
    def __init__(self, app):
        self.app = app
        self.main_message_id = None
        self.notification_entity = LIGHT_MONITOR_CONFIG.get("notification_entity", "notify.102_info_dom_milyi_dom")

    def reset_message_id(self):
        """Сброс ID сообщения (например, при команде /start)"""
        self.main_message_id = None

    def render_message(self, text, inline_keyboard=None, parse_mode="markdown"):
        if self.main_message_id is None:
            response = self.app.call_service(
                "telegram_bot/send_message",
                entity_id=self.notification_entity,
                message=text,
                parse_mode=parse_mode,
                inline_keyboard=inline_keyboard,
            )

            try:
                if response and "result" in response:
                    self.main_message_id = response["result"]["response"]["chats"][0]["message_id"]
            except Exception as e:
                self.app.log(f"ERROR SAVE MESSAGE ID: {e}")
        else:
            self.app.call_service(
                "telegram_bot/edit_message",
                entity_id=self.notification_entity,
                message_id=self.main_message_id,
                message=text,
                parse_mode=parse_mode,
                inline_keyboard=inline_keyboard
            )

    def send_notification(self, text, inline_keyboard=None):
        """Отправляет новое сообщение (например, уведомление), возвращает message_id"""
        response = self.app.call_service(
            "telegram_bot/send_message",
            entity_id=self.notification_entity,
            message=text,
            inline_keyboard=inline_keyboard
        )
        if response and "result" in response:
            return response["result"]["response"]["chats"][0]["message_id"]
        return None

    def edit_notification(self, message_id, text, inline_keyboard=None):
        """Редактирует или удаляет уведомление"""
        self.app.call_service(
            "telegram_bot/edit_message",
            entity_id=self.notification_entity,
            message_id=message_id,
            message=text,
            inline_keyboard=inline_keyboard or []
        )
