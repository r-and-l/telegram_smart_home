import logging
import json
import os
from config import LIGHT_MONITOR_CONFIG

class TelegramAPI:
    def __init__(self, app):
        self.app = app
        self.notification_entity = LIGHT_MONITOR_CONFIG.get("notification_entity", "notify.102_info_dom_milyi_dom")
        self.state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state.json")
        self.main_message_id = self._load_message_id()
        self.last_text = None
        self.last_keyboard = None
        self.last_parse_mode = None

    def _load_message_id(self):
        """Загружает сохраненный ID сообщения из файла"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    val = data.get("main_message_id")
                    self.app.log(f"LOADED PERSISTED MESSAGE ID FROM state.json: {val}")
                    return val
        except Exception as e:
            self.app.log(f"Error loading persisted state: {e}")
        return None

    def _save_message_id(self, message_id):
        """Сохраняет ID сообщения в файл"""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({"main_message_id": message_id}, f)
        except Exception as e:
            self.app.log(f"Error saving persisted state: {e}")

    def reset_message_id(self):
        """Сброс ID сообщения (например, при команде /start)"""
        self.main_message_id = None
        self._save_message_id(None)
        self.last_text = None
        self.last_keyboard = None
        self.last_parse_mode = None

    def render_message(self, text, inline_keyboard=None, parse_mode="markdown"):
        # Предотвращаем отправку запроса, если сообщение не изменилось
        if (self.main_message_id is not None and 
            self.last_text == text and 
            self.last_keyboard == inline_keyboard and
            self.last_parse_mode == parse_mode):
            return

        self.last_text = text
        self.last_keyboard = inline_keyboard
        self.last_parse_mode = parse_mode

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
                    self._save_message_id(self.main_message_id)
            except Exception as e:
                self.app.log(f"ERROR SAVE MESSAGE ID: {e}")
        else:
            try:
                self.app.call_service(
                    "telegram_bot/edit_message",
                    entity_id=self.notification_entity,
                    message_id=self.main_message_id,
                    message=text,
                    parse_mode=parse_mode,
                    inline_keyboard=inline_keyboard
                )
            except Exception as e:
                self.app.log(f"Failed to edit message {self.main_message_id}, sending new one instead: {e}")
                # Если редактирование не удалось (например, сообщение удалено в ТГ), сбрасываем ID и отправляем заново
                self.main_message_id = None
                self._save_message_id(None)
                # Рекурсивно вызываем себя же, чтобы отправить новое сообщение
                self.render_message(text, inline_keyboard, parse_mode)

    def send_notification(self, text, inline_keyboard=None, parse_mode="markdown"):
        """Отправляет новое сообщение (например, уведомление), возвращает message_id"""
        response = self.app.call_service(
            "telegram_bot/send_message",
            entity_id=self.notification_entity,
            message=text,
            parse_mode=parse_mode,
            inline_keyboard=inline_keyboard
        )
        if response and "result" in response:
            return response["result"]["response"]["chats"][0]["message_id"]
        return None

    def edit_notification(self, message_id, text, inline_keyboard=None, parse_mode="markdown"):
        """Редактирует или удаляет уведомление"""
        self.app.call_service(
            "telegram_bot/edit_message",
            entity_id=self.notification_entity,
            message_id=message_id,
            message=text,
            parse_mode=parse_mode,
            inline_keyboard=inline_keyboard or []
        )

    def delete_notification(self, message_id):
        """Удаляет уведомление. Если не удается удалить, редактирует его, заменяя текст на статус."""
        try:
            self.app.call_service(
                "telegram_bot/delete_message",
                entity_id=self.notification_entity,
                message_id=message_id
            )
        except Exception as e:
            self.app.log(f"Failed to delete message {message_id}, editing instead: {e}")
            try:
                self.edit_notification(message_id, "✅ Выключено")
            except Exception as e2:
                self.app.log(f"Failed to edit message fallback: {e2}")
