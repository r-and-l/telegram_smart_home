from config import CATEGORIES, BREATHER_ENTITY
from core import devices
from ui.views import (
    build_keyboard,
    build_menu_rich_blocks,
    build_sensor_extra_text,
    build_climate_sensors_rich_blocks,
    build_rich_paragraph,
    build_rich_section_heading,
    build_ac_text,
    build_ac_keyboard,
    build_ac_rich_blocks,
    build_timers_rich_blocks,
    build_timers_keyboard,
    build_timer_edit_rich_blocks,
    build_timer_edit_keyboard,
)
from ui.keyboards import MAIN_KEYBOARD_INLINE


class Menu:
    """Базовый класс для всех меню"""
    def __init__(self, app, category, title):
        self.app = app
        self.category = category
        self.title = title

    def render(self):
        """Возвращает кортеж (rich_blocks, fallback_text, inline_keyboard, parse_mode)"""
        raise NotImplementedError


class TableMenu(Menu):
    """Стандартное меню с таблицей управляемых устройств и кнопками-переключателями"""
    def render(self):
        control_devices = devices.controllable(self.category)

        blocks, fallback_text = build_menu_rich_blocks(self.app, self.title, control_devices)

        buttons = [
            (name, f"/menu:ac:{entity}" if entity.startswith("climate.") else f"/toggle:{entity}")
            for name, entity in control_devices
        ]
        buttons.append(("⬅️ Назад", "/back"))

        return blocks, fallback_text, build_keyboard(buttons, 3), "html"


class ClimateMenu(TableMenu):
    """Климатическое меню с таблицей управления и таблицей датчиков под ней"""
    def render(self):
        blocks, fallback_text, inline_keyboard, parse_mode = super().render()

        sensor_items = [d for d in devices.by_type(self.category) if d.get("is_sensor")]
        sensor_block, sensor_fallback = build_climate_sensors_rich_blocks(self.app, sensor_items)
        if sensor_block:
            blocks.append(build_rich_paragraph("🌡️ Датчики"))
            blocks.append(sensor_block)
            fallback_text += sensor_fallback

        return blocks, fallback_text, inline_keyboard, parse_mode


class WeatherMenu(Menu):
    """Погодное меню, отображающее список датчиков простым текстом"""
    def render(self):
        clean_title = self.title.replace("*", "").replace("\n\n", "\n").strip()

        blocks = [build_rich_section_heading(clean_title)]
        lines = [clean_title]

        for name, entity in devices.controllable(self.category):
            value = build_sensor_extra_text(self.app, name, entity, self.app.get_state(entity))
            lines.append(f"{name}: {value}")
            blocks.append(build_rich_paragraph(f"{name}: {value}"))

        inline_keyboard = build_keyboard([("⬅️ Назад", "/back")], 2)
        return blocks, "\n".join(lines) + "\n", inline_keyboard, "html"


class ACMenu(Menu):
    """Меню управления кондиционером"""
    def __init__(self, app, entity_id, sub_menu=None):
        self.app = app
        self.entity_id = entity_id
        self.sub_menu = sub_menu

    def render(self):
        name = devices.name_of(self.entity_id, default="Кондиционер")

        state = self.app.get_state(self.entity_id)
        current_temp = self.app.get_state(self.entity_id, attribute="current_temperature")
        target_temp = self.app.get_state(self.entity_id, attribute="temperature")
        fan_mode = self.app.get_state(self.entity_id, attribute="fan_mode")

        breather_state = self.app.get_state(BREATHER_ENTITY)
        breather_mode = self.app.get_state(BREATHER_ENTITY, attribute="preset_mode")

        # Запоминаем последний рабочий режим, чтобы кнопка «Включить» его восстановила
        if state and str(state).lower() != "off":
            self.app.last_ac_modes[self.entity_id] = str(state).lower()
        last_mode = self.app.last_ac_modes.get(self.entity_id, "cool")

        args = (name, state, current_temp, target_temp, fan_mode, breather_state, breather_mode)
        blocks = build_ac_rich_blocks(*args, last_mode=last_mode)
        fallback_text = build_ac_text(*args, last_mode=last_mode)
        inline_keyboard = build_ac_keyboard(self.entity_id, sub_menu=self.sub_menu, state=state)

        return blocks, fallback_text, inline_keyboard, "html"


class TimersMenu(Menu):
    """Список таймеров света с переходом к настройке конкретной комнаты"""
    def __init__(self, app, light_monitor):
        self.app = app
        self.light_monitor = light_monitor

    def render(self):
        overview = self.light_monitor.timers_overview()
        blocks, fallback_text = build_timers_rich_blocks(overview)
        return blocks, fallback_text, build_timers_keyboard(overview), "html"


class TimerEditMenu(Menu):
    """Настройка таймера одной комнаты кнопками, без правки config.py"""
    def __init__(self, app, light_monitor, entity_id):
        self.app = app
        self.light_monitor = light_monitor
        self.entity_id = entity_id

    def render(self):
        entity = self.entity_id
        minutes = self.light_monitor.timer_minutes(entity)
        default_minutes = self.light_monitor.default_timer_minutes(entity)
        blocks, fallback_text = build_timer_edit_rich_blocks(
            devices.name_of(entity),
            minutes,
            default_minutes,
            self.app.get_state(entity) == "on",
        )
        keyboard = build_timer_edit_keyboard(entity, minutes, default_minutes)
        return blocks, fallback_text, keyboard, "html"


class MenuManager:
    # Префиксы меню, которые несут в себе entity_id: "префикс:" -> (builder_key, sub_menu)
    _AC_SUBMENUS = (
        ("ac_modes:", "modes"),
        ("ac_breather:", "breather"),
        ("ac:", None),
    )

    def __init__(self, app, telegram_api, light_monitor=None):
        self.app = app
        self.telegram = telegram_api
        self.light_monitor = light_monitor
        self.current_menu = None

        if not hasattr(self.app, "last_ac_modes"):
            self.app.last_ac_modes = {}

        # Декларативная регистрация статических разделов меню
        self.menus = {
            "lights": TableMenu(app, "lights", CATEGORIES["lights"]["title"]),
            "climate": ClimateMenu(app, "climate", CATEGORIES["climate"]["title"]),
            "blinds": TableMenu(app, "blinds", CATEGORIES["blinds"]["title"]),
            "weather": WeatherMenu(app, "weather", CATEGORIES["weather"]["title"]),
        }
        if light_monitor is not None:
            self.menus["timers"] = TimersMenu(app, light_monitor)

        # Слушатели изменений состояний и атрибутов для всех сущностей из конфига
        for entity in devices.all_monitored_entities():
            self.app.listen_state(self._entity_state_changed, entity, attribute="all")
        self.app.listen_state(self._entity_state_changed, BREATHER_ENTITY, attribute="all")

    # ───────────── Реакция на изменения состояний ─────────────

    def _entity_state_changed(self, entity, attribute, old, new, kwargs):
        """Перерисовывает открытое меню, если изменилась относящаяся к нему сущность"""
        if self.current_menu is None or self.telegram.main_message_id is None or old == new:
            return

        menu_key = self.current_menu

        if menu_key.startswith("ac"):
            ac_entity = menu_key.split(":", 1)[-1]
            if entity in (ac_entity, BREATHER_ENTITY):
                self._render_current_menu()
            return

        if menu_key == "timers" or menu_key.startswith("timer_edit:"):
            device = devices.by_entity(entity)
            if device and device.get("type") == "lights":
                self._render_current_menu()
            return

        device = devices.by_entity(entity)
        if device and device.get("type") == menu_key:
            self._render_current_menu()

    # ───────────── Навигация ─────────────

    def show_main_menu(self):
        """Показывает главное меню"""
        self.current_menu = None
        blocks = [build_rich_section_heading("🏠 Умный дом"), build_rich_paragraph("Выбери раздел:")]
        self.telegram.render_message(
            text="🏠 <b>Умный дом</b>\n\nВыбери раздел:",
            inline_keyboard=MAIN_KEYBOARD_INLINE,
            parse_mode="html",
            rich_blocks=blocks
        )

    def show_menu(self, category):
        """Отображает конкретное меню (освещение, климат, таймеры и т.д.)"""
        self.current_menu = category
        self._render_current_menu()

    def show_ac_menu(self, entity_id):
        self.show_menu(f"ac:{entity_id}")

    def show_ac_modes_menu(self, entity_id):
        self.show_menu(f"ac_modes:{entity_id}")

    def show_ac_breather_menu(self, entity_id):
        self.show_menu(f"ac_breather:{entity_id}")

    def show_timer_edit_menu(self, entity_id):
        self.show_menu(f"timer_edit:{entity_id}")

    def refresh(self):
        """Перерисовывает текущее меню, если оно открыто"""
        if self.current_menu:
            self._render_current_menu()

    def auto_update(self, kwargs):
        """Раз в минуту обновляет сообщение, если в открытом меню есть горящий свет (для счетчика времени)"""
        if self.current_menu is None or self.telegram.main_message_id is None:
            return

        if self.current_menu != "lights":
            return

        if any(self.app.get_state(entity) == "on" for _name, entity in devices.controllable("lights")):
            self._render_current_menu()

    # ───────────── Рендеринг ─────────────

    def _resolve_menu(self):
        """Возвращает объект меню для текущего ключа current_menu"""
        key = self.current_menu

        for prefix, sub_menu in self._AC_SUBMENUS:
            if key.startswith(prefix):
                return ACMenu(self.app, key[len(prefix):], sub_menu=sub_menu)

        if key.startswith("timer_edit:") and self.light_monitor is not None:
            return TimerEditMenu(self.app, self.light_monitor, key[len("timer_edit:"):])

        return self.menus.get(key)

    def _render_current_menu(self):
        """Рендерит текущее открытое меню через соответствующий класс"""
        menu = self._resolve_menu()
        if not menu:
            return

        blocks, fallback_text, inline_keyboard, parse_mode = menu.render()
        self.telegram.render_message(
            text=fallback_text,
            inline_keyboard=inline_keyboard,
            parse_mode=parse_mode,
            rich_blocks=blocks
        )
