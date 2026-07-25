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

        self.app.log(f"TelegramAPI initialized: chat_id={self.chat_id}, main_message_id={self.main_message_id}")

    # ───────────── Персистентное состояние ─────────────

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
                "chat_id": chat_id if chat_id is not None else self.chat_id,
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

    # ───────────── Вызовы HA telegram_bot интеграции ─────────────

    def _ha_send_message(self, text, inline_keyboard=None, parse_mode="html"):
        """Отправляет текстовое сообщение через HA-интеграцию."""
        kwargs = {"message": text, "parse_mode": parse_mode}
        if inline_keyboard is not None:
            kwargs["inline_keyboard"] = inline_keyboard
        if self.chat_id:
            kwargs["chat_id"] = self.chat_id
            
        self.app.log(f"📤 SENDING MESSAGE via HA")
        response = self.app.call_service("telegram_bot/send_message", **kwargs)
        try:
            if response and "result" in response:
                msg_id = response["result"]["response"]["chats"][0]["message_id"]
                self.app.log(f"📤 HA message sent, message_id={msg_id}")
                return msg_id
        except Exception as e:
            self.app.log(f"ERROR getting message_id from HA response: {e}")
        return None

    def _ha_edit_message(self, message_id, text, inline_keyboard=None, parse_mode="html"):
        """Редактирует сообщение через HA-интеграцию в месте его расположения."""
        kwargs = {
            "message_id": message_id,
            "message": text,
            "parse_mode": parse_mode,
            "inline_keyboard": inline_keyboard or []
        }
        if self.chat_id:
            kwargs["chat_id"] = self.chat_id
        self.app.log(f"✏️ EDITING MESSAGE via HA (message_id: {message_id})")
        try:
            self.app.call_service("telegram_bot/edit_message", **kwargs)
        except Exception as e:
            self.app.log(f"HA edit_message failed for {message_id}: {e}")

    def pin_main_message(self):
        """Закрепляет главное сообщение в чате."""
        if not self.main_message_id:
            return
        try:
            kwargs = {
                "message_id": self.main_message_id,
                "disable_notification": True
            }
            if self.chat_id:
                kwargs["chat_id"] = self.chat_id
            self.app.call_service("telegram_bot/pin_message", **kwargs)
            self.app.log(f"📌 Pinned main message {self.main_message_id}")
        except Exception as e:
            self.app.log(f"Failed to pin main message {self.main_message_id}: {e}")

    # ───────────── Публичный интерфейс ─────────────

    def render_message(self, text=None, inline_keyboard=None, parse_mode="html", rich_blocks=None):
        """
        Рендерит основное сообщение бота.
        Редактирует текущее закрепленное/главное сообщение.
        """
        if not text:
            return

        # Предотвращаем повторные вызовы, если текст и клавиатура не изменились
        if self.main_message_id is not None:
            if self.last_text == text and self.last_keyboard == inline_keyboard:
                return

        self.last_text = text
        self.last_keyboard = inline_keyboard

        # ─── 1. Если еще нет ID сообщения — отправляем новое и закрепляем ───
        if self.main_message_id is None:
            msg_id = self._ha_send_message(text, inline_keyboard, parse_mode)
            if msg_id:
                self.main_message_id = msg_id
                self._save_state()
                self.pin_main_message()

        # ─── 2. Если сообщение существует — редактируем его в чате ───
        else:
            try:
                self._ha_edit_message(self.main_message_id, text, inline_keyboard, parse_mode)
            except Exception as e:
                self.app.log(f"Edit failed for message {self.main_message_id}: {e}")

    def send_notification(self, text, inline_keyboard=None, parse_mode="html"):
        """Отправляет всплывающее уведомление"""
        kwargs = {"message": text, "parse_mode": parse_mode}
        if inline_keyboard is not None:
            kwargs["inline_keyboard"] = inline_keyboard
        if self.chat_id:
            kwargs["chat_id"] = self.chat_id
        try:
            self.app.log(f"🔔 SENDING NOTIFICATION...")
            response = self.app.call_service("telegram_bot/send_message", **kwargs)
            if response and "result" in response:
                return response["result"]["response"]["chats"][0]["message_id"]
        except Exception as e:
            self.app.log(f"Error sending notification: {e}")
        return None

    def edit_notification(self, message_id, text, inline_keyboard=None, parse_mode="html"):
        """Редактирует уведомление"""
        kwargs = {
            "message_id": message_id,
            "message": text,
            "parse_mode": parse_mode,
            "inline_keyboard": inline_keyboard or []
        }
        if self.chat_id:
            kwargs["chat_id"] = self.chat_id
        self.app.call_service("telegram_bot/edit_message", **kwargs)

    def delete_notification(self, message_id):
        """Удаляет уведомление"""
        try:
            kwargs = {"message_id": message_id}
            if self.chat_id:
                kwargs["chat_id"] = self.chat_id
            self.app.call_service("telegram_bot/delete_message", **kwargs)
        except Exception as e:
            self.app.log(f"Failed to delete notification {message_id}: {e}")
