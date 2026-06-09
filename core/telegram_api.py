import logging
import json
import os
from config import TELEGRAM_CONFIG

class TelegramAPI:
    def __init__(self, app):
        self.app = app
        self.state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state.json")
        state = self._load_state()
        self.main_message_id = state.get("main_message_id")
        self.chat_id = state.get("chat_id") or TELEGRAM_CONFIG.get("chat_id")
        self.last_text = None
        self.last_keyboard = None
        self.last_parse_mode = None

    def _load_state(self):
        """Загружает сохраненное состояние из файла"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.app.log(f"LOADED PERSISTED STATE: {data}")
                    return data
        except Exception as e:
            self.app.log(f"Error loading persisted state: {e}")
        return {}

    def _save_state(self, message_id=None, chat_id=None):
        """Сохраняет состояние в файл"""
        try:
            state = {
                "main_message_id": message_id if message_id is not None else self.main_message_id,
                "chat_id": chat_id if chat_id is not None else self.chat_id
            }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except Exception as e:
            self.app.log(f"Error saving persisted state: {e}")

    def update_chat_id(self, chat_id):
        """Обновляет ID чата при входящем сообщении"""
        if chat_id and self.chat_id != chat_id:
            self.chat_id = chat_id
            self._save_state()
    def reset_message_id(self):
        """Сброс ID сообщения (например, при команде /start)"""
        self.main_message_id = None
        self._save_state(message_id=None)
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
            kwargs = {
                "message": text,
                "parse_mode": parse_mode,
            }
            if inline_keyboard is not None:
                kwargs["inline_keyboard"] = inline_keyboard
            if self.chat_id:
                kwargs["target"] = self.chat_id

            response = self.app.call_service(
                "telegram_bot/send_message",
                **kwargs
            )

            try:
                if response and "result" in response:
                    self.main_message_id = response["result"]["response"]["chats"][0]["message_id"]
                    self._save_state()
            except Exception as e:
                self.app.log(f"ERROR SAVE MESSAGE ID: {e}")
        else:
            try:
                kwargs = {
                    "message_id": self.main_message_id,
                    "message": text,
                    "parse_mode": parse_mode,
                    "inline_keyboard": inline_keyboard or []
                }
                if self.chat_id:
                    kwargs["chat_id"] = self.chat_id

                self.app.call_service(
                    "telegram_bot/edit_message",
                    **kwargs
                )
            except Exception as e:
                self.app.log(f"Failed to edit message {self.main_message_id}, sending new one instead: {e}")
                # Если редактирование не удалось (например, сообщение удалено в ТГ), сбрасываем ID и отправляем заново
                self.main_message_id = None
                self._save_state()
                # Рекурсивно вызываем себя же, чтобы отправить новое сообщение
                self.render_message(text, inline_keyboard, parse_mode)

    def send_notification(self, text, inline_keyboard=None, parse_mode="markdown"):
        """Отправляет новое сообщение (например, уведомление), возвращает message_id"""
        kwargs = {
            "message": text,
            "parse_mode": parse_mode
        }
        if inline_keyboard is not None:
            kwargs["inline_keyboard"] = inline_keyboard
            
        if self.chat_id:
            kwargs["target"] = self.chat_id

        response = self.app.call_service(
            "telegram_bot/send_message",
            **kwargs
        )
        if response and "result" in response:
            return response["result"]["response"]["chats"][0]["message_id"]
        return None

    def edit_notification(self, message_id, text, inline_keyboard=None, parse_mode="markdown"):
        """Редактирует или удаляет уведомление"""
        kwargs = {
            "message_id": message_id,
            "message": text,
            "parse_mode": parse_mode,
            "inline_keyboard": inline_keyboard or []
        }
        if self.chat_id:
            kwargs["chat_id"] = self.chat_id

        self.app.call_service(
            "telegram_bot/edit_message",
            **kwargs
        )

    def delete_notification(self, message_id):
        """Удаляет уведомление. Если не удается удалить, редактирует его, заменяя текст на статус."""
        try:
            kwargs = {
                "message_id": message_id
            }
            if self.chat_id:
                kwargs["chat_id"] = self.chat_id

            self.app.call_service(
                "telegram_bot/delete_message",
                **kwargs
            )
        except Exception as e:
            self.app.log(f"Failed to delete message {message_id}, editing instead: {e}")
            try:
                self.edit_notification(message_id, "✅ Выключено")
            except Exception as e2:
                self.app.log(f"Failed to edit message fallback: {e2}")
