import json
import time
import urllib.error
import urllib.request
from config import TELEGRAM_CONFIG
from core.store import Store


class TelegramAPI:
    def __init__(self, app, store=None):
        self.app = app
        self.store = store or Store(app)
        self.main_message_id = self.store.get("main_message_id")
        self.chat_id = self.store.get("chat_id") or TELEGRAM_CONFIG.get("chat_id")
        self.bot_token = TELEGRAM_CONFIG.get("bot_token")
        self.last_text = None
        self.last_keyboard = None
        self._opener = self._build_opener()

        self.app.log(
            f"TelegramAPI initialized: bot_token={'SET' if self.bot_token else 'NOT SET'}, "
            f"chat_id={self.chat_id}, main_message_id={self.main_message_id}"
        )

    # ───────────── Персистентное состояние ─────────────

    def _save_state(self):
        """Сохраняет id главного сообщения и чата в общее хранилище"""
        self.store.update(main_message_id=self.main_message_id, chat_id=self.chat_id)

    def update_chat_id(self, chat_id):
        """Обновляет ID чата при входящем сообщении"""
        if chat_id and self.chat_id != chat_id:
            self.chat_id = chat_id
            self._save_state()

    def reset_message_id(self):
        """Сброс ID сообщения (например, при команде /start)"""
        self.main_message_id = None
        self._save_state()
        self.last_text = None
        self.last_keyboard = None

    # ───────────── Прямые вызовы Telegram Bot API (Rich Tables) ─────────────

    def _build_opener(self):
        """Создаёт urllib opener: прямое подключение или через прокси из TELEGRAM_CONFIG."""
        proxy = TELEGRAM_CONFIG.get("proxy")
        if isinstance(proxy, list):
            proxy = proxy[0] if proxy else None

        if not proxy or not isinstance(proxy, str):
            return urllib.request.build_opener()

        if proxy.startswith("http://") or proxy.startswith("https://"):
            self.app.log(f"[PROXY] Using HTTP proxy: {proxy}")
            return urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            )

        if proxy.startswith("socks5://") or proxy.startswith("socks5h://"):
            try:
                import socks
                from sockshandler import SocksiPyHandler
            except ImportError:
                self.app.log("[SETUP] Installing PySocks for proxy...")
                import subprocess
                subprocess.check_call(["pip", "install", "-q", "PySocks"])
                import socks
                from sockshandler import SocksiPyHandler

            use_remote_dns = proxy.startswith("socks5h://")
            clean_addr = proxy.replace("socks5h://", "").replace("socks5://", "")
            username = password = None
            if "@" in clean_addr:
                creds, clean_addr = clean_addr.rsplit("@", 1)
                if ":" in creds:
                    username, password = creds.split(":", 1)
            host, port = clean_addr.split(":")
            self.app.log(f"[PROXY] Using SOCKS5 proxy: {host}:{port}")
            return urllib.request.build_opener(
                SocksiPyHandler(
                    socks.SOCKS5,
                    host,
                    int(port),
                    rdns=use_remote_dns,
                    username=username,
                    password=password,
                )
            )

        return urllib.request.build_opener()

    def _tg_api(self, method, payload, timeout=5, quiet=False):
        """Выполняет прямой HTTP-запрос к Telegram Bot API."""
        if not self.bot_token:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        t0 = time.monotonic()
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                dur = time.monotonic() - t0
                result = json.loads(resp.read().decode("utf-8"))
                self.app.log(f"[OK] Telegram API {method} OK ({int(dur * 1000)}ms)")
                return result
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if not quiet:
                self.app.log(f"[ERROR] Telegram API error {e.code} for {method}: {body}")
            try:
                return json.loads(body)
            except Exception:
                return {"ok": False, "error_code": e.code, "description": body}
        except Exception as e:
            if not quiet:
                self.app.log(f"[ERROR] Telegram API call {method} failed: {e}")
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

    def _send_rich_message(self, blocks=None, inline_keyboard=None, rich_html=None):
        """Отправляет Rich Message — через HTML (кнопки в теле) или blocks + inline_keyboard."""
        payload = {"chat_id": self.chat_id}

        if rich_html:
            payload["rich_message"] = {"html": rich_html}
        else:
            payload["rich_message"] = {"blocks": blocks}
            markup = self._build_inline_markup(inline_keyboard)
            if markup:
                payload["reply_markup"] = markup

        self.app.log(f"[SEND] RICH MESSAGE to chat {self.chat_id}")
        result = self._tg_api("sendRichMessage", payload)
        if result and result.get("ok"):
            msg_id = result["result"]["message_id"]
            self.app.log(f"[SEND] Rich message sent, message_id={msg_id}")
            return msg_id
        return None

    def _edit_rich_message(self, message_id, blocks=None, inline_keyboard=None, rich_html=None):
        """
        Редактирует Rich Message — через HTML или blocks.
        Возвращает True при успехе (включая 'message is not modified'),
        'missing' если сообщение было удалено из чата, и False при ошибке.
        """
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
        }

        if rich_html:
            payload["rich_message"] = {"html": rich_html}
        else:
            payload["rich_message"] = {"blocks": blocks}
            markup = self._build_inline_markup(inline_keyboard)
            if markup:
                payload["reply_markup"] = markup

        self.app.log(f"[EDIT] RICH MESSAGE (message_id: {message_id})")
        result = self._tg_api("editMessageText", payload)
        if result and result.get("ok"):
            return True
        if result is not None:
            desc = str(result.get("description", "")).lower()
            if "message is not modified" in desc:
                return True
            if "message to edit not found" in desc or "message_id_invalid" in desc:
                return "missing"
        return False

    # ───────────── Вызовы HA telegram_bot интеграции (Fallback) ─────────────

    def _ha_send_message(self, text, inline_keyboard=None, parse_mode="html"):
        """Отправляет текстовое сообщение через HA-интеграцию."""
        kwargs = {"message": text, "parse_mode": parse_mode}
        if inline_keyboard is not None:
            kwargs["inline_keyboard"] = inline_keyboard
        if self.chat_id:
            kwargs["chat_id"] = self.chat_id

        self.app.log("[SEND] MESSAGE via HA")
        response = self.app.call_service("telegram_bot/send_message", **kwargs)
        try:
            if response and "result" in response:
                msg_id = response["result"]["response"]["chats"][0]["message_id"]
                self.app.log(f"[SEND] HA message sent, message_id={msg_id}")
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
            "inline_keyboard": inline_keyboard or [],
        }
        if self.chat_id:
            kwargs["chat_id"] = self.chat_id
        self.app.log(f"[EDIT] MESSAGE via HA (message_id: {message_id})")
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
                "disable_notification": True,
            }
            if self.chat_id:
                kwargs["chat_id"] = self.chat_id
            self.app.call_service("telegram_bot/pin_message", **kwargs)
            self.app.log(f"[PIN] Pinned main message {self.main_message_id}")
        except Exception as e:
            self.app.log(f"Failed to pin main message {self.main_message_id}: {e}")

    # ───────────── Публичный интерфейс ─────────────

    def render_message(self, text=None, inline_keyboard=None, parse_mode="html",
                       rich_blocks=None, rich_html=None):
        """
        Рендерит основное сообщение бота.

        Один вызов к Telegram API (rich_html ИЛИ rich_blocks), при отсутствии
        bot_token — fallback через HA.
        """
        compare_key = rich_html or (
            json.dumps(rich_blocks, ensure_ascii=False, sort_keys=True) if rich_blocks else text
        )

        if self.main_message_id is not None:
            if self.last_text == compare_key and self.last_keyboard == inline_keyboard:
                return

        can_use_api = bool(self.bot_token and self.chat_id)

        # ─── 2. Если сообщение существует — редактируем ───
        if self.main_message_id is not None:
            status = False

            if can_use_api:
                if rich_html:
                    status = self._edit_rich_message(self.main_message_id, rich_html=rich_html)
                elif rich_blocks:
                    status = self._edit_rich_message(
                        self.main_message_id, blocks=rich_blocks, inline_keyboard=inline_keyboard
                    )
                if status == "missing":
                    self.app.log(f"[WARN] Main message {self.main_message_id} not found in chat, recreating")
                    self.reset_message_id()
                else:
                    if status:
                        self.last_text = compare_key
                        self.last_keyboard = inline_keyboard
                    return
            elif text:
                self._ha_edit_message(self.main_message_id, text, inline_keyboard, parse_mode)
                self.last_text = compare_key
                self.last_keyboard = inline_keyboard
                return

        # ─── 1. Если ещё нет сообщения (или оно было удалено) — отправляем новое и закрепляем ───
        if self.main_message_id is None:
            msg_id = None

            if can_use_api:
                if rich_html:
                    msg_id = self._send_rich_message(rich_html=rich_html)
                elif rich_blocks:
                    msg_id = self._send_rich_message(blocks=rich_blocks, inline_keyboard=inline_keyboard)
            elif text:
                msg_id = self._ha_send_message(text, inline_keyboard, parse_mode)

            if msg_id:
                self.main_message_id = msg_id
                self.last_text = compare_key
                self.last_keyboard = inline_keyboard
                self._save_state()
                self.pin_main_message()

    def send_notification(self, text, inline_keyboard=None, parse_mode="html",
                          rich_html=None, rich_blocks=None):
        """
        Отправляет всплывающее уведомление (поддерживает Rich HTML таблицы с fallback на sendMessage).
        Возвращает message_id или None.
        """
        if self.bot_token and self.chat_id:
            if rich_html or rich_blocks:
                msg_id = self._send_rich_message(
                    blocks=rich_blocks,
                    inline_keyboard=inline_keyboard,
                    rich_html=rich_html,
                )
                if msg_id:
                    return msg_id
            payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            markup = self._build_inline_markup(inline_keyboard)
            if markup:
                payload["reply_markup"] = markup
            result = self._tg_api("sendMessage", payload)
            if result and result.get("ok"):
                return result["result"]["message_id"]
            return None

        kwargs = {"message": text, "parse_mode": parse_mode}
        if inline_keyboard is not None:
            kwargs["inline_keyboard"] = inline_keyboard
        if self.chat_id:
            kwargs["chat_id"] = self.chat_id
        try:
            self.app.log("[NOTIF] SENDING NOTIFICATION via HA")
            response = self.app.call_service("telegram_bot/send_message", **kwargs)
            if response and "result" in response:
                return response["result"]["response"]["chats"][0]["message_id"]
        except Exception as e:
            self.app.log(f"Error sending notification: {e}")
        return None

    def edit_notification(self, message_id, text, inline_keyboard=None, parse_mode="html"):
        """Редактирует уведомление. Возвращает True при успехе."""
        if self.bot_token and self.chat_id:
            payload = {
                "chat_id": self.chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
            }
            markup = self._build_inline_markup(inline_keyboard)
            payload["reply_markup"] = markup or {"inline_keyboard": []}
            result = self._tg_api("editMessageText", payload)
            if result and result.get("ok"):
                return True
            if result and "message is not modified" in str(result.get("description", "")).lower():
                return True
            return False

        kwargs = {
            "message_id": message_id,
            "message": text,
            "parse_mode": parse_mode,
            "inline_keyboard": inline_keyboard or [],
        }
        if self.chat_id:
            kwargs["chat_id"] = self.chat_id
        try:
            self.app.call_service("telegram_bot/edit_message", **kwargs)
            return True
        except Exception as e:
            self.app.log(f"Failed to edit notification {message_id}: {e}")
            return False

    def delete_notification(self, message_id):
        """
        Удаляет уведомление.
        Возвращает True, если сообщения в чате больше нет (удалено сейчас
        или отсутствовало), и False, если удалить не удалось — тогда вызов
        стоит повторить позже.
        """
        if self.bot_token and self.chat_id:
            result = self._tg_api(
                "deleteMessage",
                {"chat_id": self.chat_id, "message_id": message_id},
                quiet=True,
            )
            if result and result.get("ok"):
                self.app.log(f"[DEL] Deleted notification {message_id}")
                return True
            if result is not None:
                description = str(result.get("description", "")).lower()
                if any(marker in description for marker in (
                    "message to delete not found",
                    "message identifier is not specified",
                    "message_id_invalid",
                )):
                    self.app.log(f"[DEL] Notification {message_id} already gone: {description}")
                    return True
                if "message can't be deleted" in description:
                    self.app.log(f"[DEL] Notification {message_id} too old to delete, clearing buttons")
                    self.edit_notification(message_id, "✅ Свет выключен", inline_keyboard=[])
                    return True
                self.app.log(f"[ERROR] Failed to delete notification {message_id}: {description}")
            return False

        try:
            kwargs = {"message_id": message_id}
            if self.chat_id:
                kwargs["chat_id"] = self.chat_id
            self.app.call_service("telegram_bot/delete_message", **kwargs)
            return True
        except Exception as e:
            self.app.log(f"Failed to delete notification {message_id}: {e}")
            return False
