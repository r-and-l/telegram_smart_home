from core import devices
from ui.keyboards import MAIN_KEYBOARD_INLINE
from ui.views import build_rich_paragraph, build_rich_section_heading


class Automations:
    def __init__(self, app, telegram_api, menu_manager):
        self.app = app
        self.telegram = telegram_api
        self.menu_manager = menu_manager

    def activate_night_mode(self):
        """Активирует ночной режим - выключает свет и закрывает шторы"""
        for _name, entity in devices.controllable("lights"):
            self.app.call_service("homeassistant/turn_off", entity_id=entity)

        for _name, entity in devices.controllable("blinds"):
            self.app.call_service("cover/close_cover", entity_id=entity)

        self.menu_manager.current_menu = None
        self.telegram.render_message(
            text="🌙 <b>Ночной режим активирован</b>\n\n✅ Свет выключен\n✅ Шторы закрыты",
            inline_keyboard=MAIN_KEYBOARD_INLINE,
            parse_mode="html",
            rich_blocks=[
                build_rich_section_heading("🌙 Ночной режим активирован"),
                build_rich_paragraph("✅ Свет выключен\n✅ Шторы закрыты"),
            ],
        )
