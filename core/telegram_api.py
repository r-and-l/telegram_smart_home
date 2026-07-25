import json
import os
import urllib.request
import urllib.error
from config import TELEGRAM_CONFIG

class TelegramAPI:
    def __init__(self, app):
        self.app = app
        self.state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state.json")
        state = self._load_state()
        self.main_message_id = state.get("main_message_id")
        self.chat_id = state.get("chat_id") or TELEGRAM_CONFIG.get("chat_id")
        self.bot_token = TELEGRAM_CONFIG.get("bot_token")
        self.last_text = None
        self.last_keyboard = None

        self.app.log(f"TelegramAPI initialized: bot_token={'SET' if self.bot_token else 'NOT SET'}, "
                     f"chat_id={self.chat_id}, main_message_id={self.main_message_id}")

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

    # ───────────── Прямые вызовы Telegram Bot API (Rich Tables) ─────────────

    def _tg_api(self, method, payload, timeout=5):
        """Выполняет HTTP-запрос к Telegram Bot API."""
        if not self.bot_token:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
        data = json.dumps(payload, ensure_ascii=True).encode("ascii")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                self.app.log(f"✅ Telegram API {method} OK")
                return result
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self.app.log(f"❌ Telegram API error {e.code} for {method}: {body}")
            return None
        except Exception as e:
            self.app.log(f"⚠️ Telegram API request error for {method}: {e}")
            return None

    def _build_inline_markup(self, inline_keyboard):
        """Преобразует список кнопок в формат InlineKeyboardMarkup."""
        if not inline_keyboard:
            return None
        keyboard = []
        for row in inline_keyboard:
            kb_row = []
            for item in row:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    kb_row.append({"text": item[0], "callback_data": item[1]})
                elif isinstance(item, dict):
                    kb_row.append(item)
            keyboard.append(kb_row)
        return {"inline_keyboard": keyboard}

    def _send_rich_message(self, blocks, inline_keyboard=None):
        """Отправляет Rich Message с нативными графическими таблицами Telegram."""
        payload = {
            "chat_id": self.chat_id,
            "rich_message": {"blocks": blocks}
        }
        markup = self._build_inline_markup(inline_keyboard)
        if markup:
            payload["reply_markup"] = markup

        self.app.log(f"📤 SENDING RICH TABLE MESSAGE to chat {self.chat_id}")
        result = self._tg_api("sendRichMessage", payload)
        if result and result.get("ok"):
            msg_id = result["result"]["message_id"]
            self.app.log(f"📤 Rich table message sent, message_id={msg_id}")
            return msg_id
        return None

    def _edit_rich_message(self, message_id, blocks, inline_keyboard=None):
        """Редактирует Rich Message с графическими таблицами."""
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "rich_message": {"blocks": blocks}
        }
        markup = self._build_inline_markup(inline_keyboard)
        if markup:
            payload["reply_markup"] = markup

        self.app.log(f"✏️ EDITING RICH TABLE MESSAGE (message_id: {message_id})")
        result = self._tg_api("editMessageText", payload)
        return result and result.get("ok")

    # ───────────── Вызовы HA telegram_bot интеграции (Fallback) ─────────────

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
        """Редактирует сообщение через HA-интеграцию без удаления."""
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
        Приоритет: Нативные графические таблицы Telegram (sendRichMessage / editMessageText).
        Никогда не удаляет сообщение при сбоях редактирования.
        """
        compare_key = json.dumps(rich_blocks, ensure_ascii=False, sort_keys=True) if rich_blocks else text

        if self.main_message_id is not None:
            if self.last_text == compare_key and self.last_keyboard == inline_keyboard:
                return

        self.last_text = compare_key
        self.last_keyboard = inline_keyboard

        use_rich = bool(rich_blocks and self.bot_token and self.chat_id)

        # ─── 1. Если еще нет ID сообщения — отправляем новое (таблица или текст) и закрепляем ───
        if self.main_message_id is None:
            if use_rich:
                msg_id = self._send_rich_message(rich_blocks, inline_keyboard)
                if msg_id:
                    self.main_message_id = msg_id
                    self._save_state()
                    self.pin_main_message()
                    return

            if text:
                msg_id = self._ha_send_message(text, inline_keyboard, parse_mode)
                if msg_id:
                    self.main_message_id = msg_id
                    self._save_state()
                    self.pin_main_message()

        # ─── 2. Если сообщение существует — редактируем его в чате ───
        else:
            if use_rich:
                success = self._edit_rich_message(self.main_message_id, rich_blocks, inline_keyboard)
                if success:
                    return

            if text:
                self._ha_edit_message(self.main_message_id, text, inline_keyboard, parse_mode)

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
