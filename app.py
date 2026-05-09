# pyrefly: ignore [missing-import]
import appdaemon.plugins.hass.hassapi as hass

from .config import ROOMS, CLIMATE_DEVICES
from .keyboards import MAIN_KEYBOARD
from .rooms import build_rooms_text
from .helpers import build_keyboard
from .menus import get_menu

class TelegramSmartHome(hass.Hass):

    def initialize(self):

        self.main_message_id = None
        self.current_menu = None

        self.listen_event(
            self.telegram_command,
            "telegram_command"
        )

        self.listen_event(
            self.telegram_text,
            "telegram_text"
        )

        self.listen_event(
            self.inline_callback,
            "telegram_callback"
        )

        self.run_every(
            self.auto_update,
            "now",
            60
        )

        self.log("SMART HOME BOT STARTED")

    # ==========================================
    # TELEGRAM RENDER MESSAGE
    # ==========================================

    def render_message(self, text, inline_keyboard=None):
        # =====================================
        # FIRST MESSAGE
        # =====================================
        if self.main_message_id is None:

            response = self.call_service(
                "telegram_bot/send_message",
                entity_id="notify.102_info_dom_milyi_dom",
                message=text,
                parse_mode="markdown",
                inline_keyboard=inline_keyboard,
            )

            try:
                self.main_message_id = (
                    response["result"]["response"]["chats"][0]["message_id"]
                )

            except Exception as e:
                self.log(f"ERROR SAVE MESSAGE ID: {e}")
        # =====================================
        # EDIT EXISTING
        # =====================================
        else:
            self.call_service(
                "telegram_bot/edit_message",
                entity_id="notify.102_info_dom_milyi_dom",
                message_id=self.main_message_id,
                message=text,
                parse_mode="markdown",
                inline_keyboard=inline_keyboard
            )

    # ==========================================
    # TELEGRAM СOMMAND (/start)
    # ==========================================

    def telegram_command(self, event_name, data, kwargs):
        command = data.get("command")
        if command == "/start":
            self.show_main_menu()
            if self.main_message_id != None:
                self.main_message_id = None

    # ==========================================
    # TELEGRAM TEXT
    # ==========================================

    def telegram_text(self, event_name, data, kwargs):
        text = data.get("text", "")
        self.log(event_name)
        self.log(f"TEXT: {text}")
        
        menu_commands = {
            "💡 Свет": "lights",
            "🌡 Климат": "climate",
            # Add more here
        }
        
        if text in menu_commands:
            self.current_menu = menu_commands[text]
            menu = get_menu(self, self.current_menu)
            if menu:
                menu.show()
        elif text == "🚪 Двери":
            pass
        elif text == "🌙 Ночь":
            pass
        elif text == "📊 Статистика":
            pass
        
        # удаляем сообщение пользователя
        self.delete_user_message(data)

    # ==========================================
    # MAIN MENU
    # ==========================================

    def show_main_menu(self):
        self.call_service(
            "telegram_bot/send_message",
            entity_id="notify.102_info_dom_milyi_dom",
            message=(
                "🏠 *Умный дом*\n\n"
                "Выбери раздел:"
            ),
            parse_mode="markdown",
            keyboard=MAIN_KEYBOARD
        )

    # ==========================================
    # INLINE BUTTONS
    # ==========================================

    def inline_callback(self, event_name, data, kwargs):
        command = data.get("command", "")
        self.log(f"CALLBACK: {command}")
        if command.startswith("/toggle:"):
            entity = command.replace("/toggle:", "")
            self.call_service(
                "homeassistant/toggle",
                entity_id=entity
            )
            # Update the current menu
            if self.current_menu:
                menu = get_menu(self, self.current_menu)
                if menu:
                    menu.show()

    # =========================================================
    # DELETE USER MESSAGE
    # =========================================================

    def delete_user_message(self, data):
        try:
            message = data.get("message")
            chat_id = data.get("chat_id")
            self.log(data)
            self.log(chat_id)
            self.log(message.get("message_id") if message else "No message")

            self.call_service(
                "telegram_bot/delete_message",
                entity_id="notify.102_info_dom_milyi_dom",
                chat_id=chat_id,
                message_id="last",
            )
        except Exception as e:
            self.log(f"DELETE ERROR: {e}")

    # ==========================================
    # AUTO UPDATE
    # ==========================================

    def auto_update(self, kwargs):

        pass