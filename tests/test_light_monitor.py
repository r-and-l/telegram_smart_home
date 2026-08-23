"""
Проверка логики уведомлений и таймеров без AppDaemon и Telegram.

Запуск: python -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.store import Store  # noqa: E402
from core import devices  # noqa: E402


class FakeApp:
    """Минимальная замена appdaemon.hassapi.Hass для тестов."""

    def __init__(self):
        self.states = {}
        self.logs = []
        self.service_calls = []
        self.timers = {}
        self._handle = 0
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.last_ac_modes = {}

    def log(self, message, *args, **kwargs):
        self.logs.append(str(message))

    def get_state(self, entity, attribute=None, **kwargs):
        if attribute in (None, "state"):
            return self.states.get(entity)
        return self.states.get(f"{entity}.{attribute}")

    def set_state_value(self, entity, value):
        self.states[entity] = value

    def call_service(self, service, **kwargs):
        self.service_calls.append((service, kwargs))
        if service in ("homeassistant/turn_off", "switch/turn_off"):
            self.states[kwargs["entity_id"]] = "off"
        return None

    def listen_state(self, *args, **kwargs):
        return object()

    def listen_event(self, *args, **kwargs):
        return object()

    def run_in(self, callback, delay, **kwargs):
        self._handle += 1
        self.timers[self._handle] = (callback, delay, kwargs)
        return self._handle

    def run_every(self, *args, **kwargs):
        return object()

    def cancel_timer(self, handle):
        self.timers.pop(handle, None)

    def datetime(self):
        return self.now

    def fire_timer(self, handle):
        callback, _delay, kwargs = self.timers.pop(handle)
        callback(kwargs)


class FakeTelegram:
    """Фиксирует отправленные/удалённые сообщения; delete можно заставить падать."""

    def __init__(self, store):
        self.store = store
        self.main_message_id = 1
        self.sent = {}
        self.deleted = []
        self.edited = []
        self.next_id = 100
        self.delete_ok = True
        self.last_render = None

    def update_chat_id(self, chat_id):
        self.chat_id = chat_id

    def reset_message_id(self):
        self.main_message_id = None

    def send_notification(self, text, inline_keyboard=None, parse_mode="html"):
        self.next_id += 1
        self.sent[self.next_id] = text
        return self.next_id

    def edit_notification(self, message_id, text, inline_keyboard=None, parse_mode="html"):
        self.edited.append((message_id, text))
        self.sent[message_id] = text
        return True

    def delete_notification(self, message_id):
        if not self.delete_ok:
            return False
        self.deleted.append(message_id)
        self.sent.pop(message_id, None)
        return True

    def render_message(self, **kwargs):
        self.last_render = kwargs


class LightMonitorTestCase(unittest.TestCase):
    def setUp(self):
        from services.light_monitor import LightMonitor

        self.LightMonitor = LightMonitor
        fd, self.state_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.state_path)

        self.app = FakeApp()
        self.lights = [d["entity"] for d in devices.lights()]
        self.assertGreaterEqual(len(self.lights), 2, "нужно минимум 2 светильника в config.py")
        for entity in self.lights:
            self.app.set_state_value(entity, "off")

        self.store = Store(self.app, path=self.state_path)
        self.telegram = FakeTelegram(self.store)

    def tearDown(self):
        if os.path.exists(self.state_path):
            os.remove(self.state_path)

    def make_monitor(self):
        return self.LightMonitor(self.app, self.telegram, store=self.store)

    def turn_on(self, monitor, entity):
        self.app.set_state_value(entity, "on")
        monitor.light_state_changed(entity, "state", "off", "on", {})

    def turn_off(self, monitor, entity):
        self.app.set_state_value(entity, "off")
        monitor.light_state_changed(entity, "state", "on", "off", {})

    def fire_all_timers(self):
        for handle in list(self.app.timers.keys()):
            self.app.fire_timer(handle)

    # ───────────── Индивидуальные уведомления ─────────────

    def test_manual_off_removes_notification(self):
        monitor = self.make_monitor()
        entity = self.lights[0]

        self.turn_on(monitor, entity)
        self.fire_all_timers()
        self.assertEqual(len(monitor.notifications), 1)

        # Выключение "вручную": состояние изменилось не через Telegram
        self.turn_off(monitor, entity)
        self.assertEqual(monitor.notifications, {})
        self.assertEqual(len(self.telegram.deleted), 1)

    def test_notification_survives_reload_and_is_cleaned(self):
        """Уведомление, отправленное до перезагрузки модулей, удаляется после неё."""
        monitor = self.make_monitor()
        entity = self.lights[0]

        self.turn_on(monitor, entity)
        self.fire_all_timers()
        message_id = list(monitor.notifications.keys())[0]

        # Рестарт: новый Store из того же файла, новый LightMonitor
        self.app.timers.clear()
        fresh_store = Store(self.app, path=self.state_path)
        self.store = fresh_store
        self.assertIn(message_id, fresh_store.get("notifications", {}))

        # Свет погасили выключателем, пока бот был перезагружен
        self.app.set_state_value(entity, "off")
        monitor2 = self.LightMonitor(self.app, self.telegram, store=fresh_store)

        self.assertEqual(monitor2.notifications, {})
        self.assertIn(int(message_id), self.telegram.deleted)

    def test_reconcile_retries_failed_delete(self):
        monitor = self.make_monitor()
        entity = self.lights[0]

        self.turn_on(monitor, entity)
        self.fire_all_timers()
        message_id = int(list(monitor.notifications.keys())[0])

        self.telegram.delete_ok = False
        self.turn_off(monitor, entity)
        self.assertEqual(self.telegram.deleted, [])
        self.assertEqual(len(monitor.notifications), 1)

        self.telegram.delete_ok = True
        monitor.reconcile()
        self.assertEqual(monitor.notifications, {})
        self.assertIn(message_id, self.telegram.deleted)

    def test_reconcile_starts_timer_for_light_on_without_notification(self):
        monitor = self.make_monitor()
        entity = self.lights[0]

        self.app.set_state_value(entity, "on")  # событие listen_state пропущено
        self.app.timers.clear()
        monitor.reconcile()
        self.assertIn(entity, monitor.active_timers)

    # ───────────── Групповые уведомления ─────────────

    def test_group_notification_narrows_on_partial_off(self):
        monitor = self.make_monitor()
        first, second = self.lights[0], self.lights[1]

        self.turn_on(monitor, first)
        self.turn_on(monitor, second)
        self.fire_all_timers()

        self.assertEqual(len(monitor.notifications), 1)
        message_id = int(list(monitor.notifications.keys())[0])
        self.assertEqual(sorted(monitor.notifications[str(message_id)]), sorted([first, second]))

        # Один свет выключен вручную — сообщение остаётся, но переписывается
        self.turn_off(monitor, first)
        self.assertEqual(monitor.notifications[str(message_id)], [second])
        self.assertNotIn(message_id, self.telegram.deleted)
        self.assertTrue(self.telegram.edited)
        self.assertIn(devices.name_of(second), self.telegram.sent[message_id])

        # Второй тоже выключен — сообщение удалено
        self.turn_off(monitor, second)
        self.assertEqual(monitor.notifications, {})
        self.assertIn(message_id, self.telegram.deleted)

    def test_group_notification_replaces_individual_one(self):
        monitor = self.make_monitor()
        first, second = self.lights[0], self.lights[1]

        self.turn_on(monitor, first)
        self.fire_all_timers()  # индивидуальное уведомление по first
        individual_id = int(list(monitor.notifications.keys())[0])

        self.turn_on(monitor, second)
        self.app.now += timedelta(minutes=1)
        self.fire_all_timers()  # срабатывает second, попадает в окно группировки

        self.assertEqual(len(monitor.notifications), 1)
        self.assertIn(individual_id, self.telegram.deleted)

    def test_stale_pending_does_not_create_phantom_group(self):
        monitor = self.make_monitor()
        first, second = self.lights[0], self.lights[1]

        self.turn_on(monitor, first)
        self.fire_all_timers()
        self.turn_off(monitor, first)
        self.assertNotIn(first, monitor.pending_group_notifications)

        self.turn_on(monitor, second)
        self.fire_all_timers()
        message_id = list(monitor.notifications.keys())[0]
        self.assertEqual(monitor.notifications[message_id], [second])
        self.assertNotIn(devices.name_of(first), self.telegram.sent[int(message_id)])

    def test_group_callback_data_fits_telegram_limit(self):
        """callback_data ограничен 64 байтами — список сущностей туда не влезает."""
        monitor = self.make_monitor()
        for entity in self.lights:
            self.turn_on(monitor, entity)
        self.fire_all_timers()

        message_id = list(monitor.notifications.keys())[0]
        entities = monitor.notifications[message_id]
        self.assertGreater(len(entities), 1)

        _text, keyboard = monitor._notification_content(entities)
        for row in keyboard:
            for _label, data in row:
                self.assertLessEqual(len(data.encode("utf-8")), 64, data)

        token = keyboard[0][0][1].split(":")[-1]
        self.assertEqual(sorted(monitor.group_entities(token)), sorted(entities))

    def test_group_tokens_pruned_with_notifications(self):
        monitor = self.make_monitor()
        first, second = self.lights[0], self.lights[1]
        self.turn_on(monitor, first)
        self.turn_on(monitor, second)
        self.fire_all_timers()
        self.assertTrue(monitor.groups)

        self.turn_off(monitor, first)
        self.turn_off(monitor, second)
        self.assertEqual(monitor.notifications, {})
        self.assertEqual(monitor.groups, {})

    # ───────────── Таймеры из Telegram ─────────────

    def test_set_timer_persists_and_applies(self):
        monitor = self.make_monitor()
        entity = self.lights[0]

        self.turn_on(monitor, entity)
        monitor.set_timer_minutes(entity, 7)
        self.assertEqual(monitor.timer_minutes(entity), 7)

        handle = monitor.active_timers[entity]
        self.assertEqual(self.app.timers[handle][1], 7 * 60)

        reloaded = Store(self.app, path=self.state_path)
        self.assertEqual(reloaded.get("timers", {})[entity], 7)

    def test_set_timer_clamped_to_limits(self):
        from config import TIMER_CONFIG

        monitor = self.make_monitor()
        entity = self.lights[0]

        self.assertEqual(monitor.set_timer_minutes(entity, 100000), TIMER_CONFIG["max_minutes"])
        self.assertEqual(monitor.set_timer_minutes(entity, -50), 0)

    def test_disable_timer_removes_notification(self):
        monitor = self.make_monitor()
        entity = self.lights[0]

        self.turn_on(monitor, entity)
        self.fire_all_timers()
        self.assertEqual(len(monitor.notifications), 1)

        monitor.set_timer_minutes(entity, 0)
        self.assertEqual(monitor.notifications, {})
        self.assertNotIn(entity, monitor.active_timers)

    def test_adjust_and_reset_timer(self):
        monitor = self.make_monitor()
        entity = self.lights[0]
        default = monitor.default_timer_minutes(entity)

        monitor.adjust_timer_minutes(entity, 5)
        self.assertEqual(monitor.timer_minutes(entity), default + 5)

        monitor.reset_timer_minutes(entity)
        self.assertEqual(monitor.timer_minutes(entity), default)
        self.assertNotIn(entity, monitor.timer_overrides)

    def test_timers_overview_shape(self):
        monitor = self.make_monitor()
        overview = monitor.timers_overview()
        self.assertEqual(len(overview), len(self.lights))
        for name, entity, minutes, is_on, is_custom in overview:
            self.assertIsInstance(name, str)
            self.assertIn(entity, self.lights)
            self.assertIn(is_on, (True, False))
            self.assertIn(is_custom, (True, False))


class RouterAndViewsTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.state_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.state_path)
        self.app = FakeApp()
        for entity in devices.all_monitored_entities():
            self.app.set_state_value(entity, "off")
        self.store = Store(self.app, path=self.state_path)
        self.telegram = FakeTelegram(self.store)

        from services.light_monitor import LightMonitor
        from services.menu_manager import MenuManager
        from services.automations import Automations
        from core.router import Router

        self.monitor = LightMonitor(self.app, self.telegram, store=self.store)
        self.menu = MenuManager(self.app, self.telegram, light_monitor=self.monitor)
        self.automations = Automations(self.app, self.telegram, self.menu)
        self.router = Router(self.app, self.menu, self.monitor, self.automations, self.telegram)

    def tearDown(self):
        if os.path.exists(self.state_path):
            os.remove(self.state_path)

    def callback(self, command):
        self.router.inline_callback("telegram_callback", {"command": command, "chat_id": 42}, {})

    def test_all_menus_render(self):
        for key in ("lights", "climate", "blinds", "weather", "timers"):
            self.callback(f"/menu:{key}")
            self.assertEqual(self.menu.current_menu, key)
            self.assertIn("rich_blocks", self.telegram.last_render)
            self.assertTrue(self.telegram.last_render["text"])

    def test_timer_flow_via_callbacks(self):
        entity = devices.lights()[0]["entity"]

        self.callback(f"/timer:open:{entity}")
        self.assertEqual(self.menu.current_menu, f"timer_edit:{entity}")

        self.callback(f"/timer:set:{entity}:45")
        self.assertEqual(self.monitor.timer_minutes(entity), 45)

        self.callback(f"/timer:adjust:{entity}:-30")
        self.assertEqual(self.monitor.timer_minutes(entity), 15)

        self.callback(f"/timer:set:{entity}:0")
        self.assertIsNone(self.monitor.timer_minutes(entity))

        self.callback(f"/timer:reset:{entity}")
        self.assertEqual(self.monitor.timer_minutes(entity),
                         self.monitor.default_timer_minutes(entity))

    def test_prefix_routing_prefers_specific_menu(self):
        ac_entity = next(
            d["entity"] for d in devices.by_type("climate")
            if isinstance(d.get("entity"), str) and d["entity"].startswith("climate.")
        )
        self.callback(f"/menu:ac_modes:{ac_entity}")
        self.assertEqual(self.menu.current_menu, f"ac_modes:{ac_entity}")

        self.callback(f"/menu:ac:{ac_entity}")
        self.assertEqual(self.menu.current_menu, f"ac:{ac_entity}")

    def test_malformed_ac_command_does_not_raise(self):
        self.callback("/ac:temp:climate.broken")
        self.callback("/ac:fan:")
        self.callback("/unknown:command")

    def test_turn_off_via_notification_button(self):
        entity = devices.lights()[0]["entity"]
        self.app.set_state_value(entity, "on")
        self.monitor.light_state_changed(entity, "state", "off", "on", {})
        for handle in list(self.app.timers.keys()):
            self.app.fire_timer(handle)
        self.assertEqual(len(self.monitor.notifications), 1)

        self.callback(f"/turn_off:{entity}")
        self.assertEqual(self.monitor.notifications, {})
        self.assertIn(("homeassistant/turn_off", {"entity_id": entity}), self.app.service_calls)

    def test_turn_off_group_via_token(self):
        lights = [d["entity"] for d in devices.lights()][:2]
        for entity in lights:
            self.app.set_state_value(entity, "on")
            self.monitor.light_state_changed(entity, "state", "off", "on", {})
        for handle in list(self.app.timers.keys()):
            self.app.fire_timer(handle)

        token = next(iter(self.monitor.groups))
        self.callback(f"/turn_off_group:{token}")

        for entity in lights:
            self.assertEqual(self.app.get_state(entity), "off")
        self.assertEqual(self.monitor.notifications, {})

    def test_unknown_group_token_is_ignored(self):
        self.callback("/turn_off_group:999")
        self.assertEqual(self.app.service_calls, [])

    def test_night_mode_turns_off_lights_and_closes_blinds(self):
        self.callback("/night_mode")
        turned_off = [c for c in self.app.service_calls if c[0] == "homeassistant/turn_off"]
        closed = [c for c in self.app.service_calls if c[0] == "cover/close_cover"]
        self.assertEqual(len(turned_off), len(devices.controllable("lights")))
        self.assertEqual(len(closed), len(devices.controllable("blinds")))


class ConfigExampleTestCase(unittest.TestCase):
    """config.example.py не импортируется приложением, поэтому проверяем его отдельно."""

    def load_example(self):
        import importlib.util

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config.example.py")
        spec = importlib.util.spec_from_file_location("config_example", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_example_has_everything_the_code_reads(self):
        example = self.load_example()
        for name in ("DEVICES", "CATEGORIES", "BREATHER_ENTITY",
                     "LIGHT_MONITOR_CONFIG", "TIMER_CONFIG", "TELEGRAM_CONFIG"):
            self.assertTrue(hasattr(example, name), f"в примере нет {name}")

        self.assertIn("group_notification_window", example.LIGHT_MONITOR_CONFIG)
        self.assertIn("reconcile_interval", example.LIGHT_MONITOR_CONFIG)
        for key in ("min_minutes", "max_minutes", "steps"):
            self.assertIn(key, example.TIMER_CONFIG)

    def test_example_devices_are_well_formed(self):
        example = self.load_example()
        for device in example.DEVICES:
            for field in ("name", "entity", "type", "room"):
                self.assertIn(field, device, device)
            self.assertIn(device["type"], example.CATEGORIES, device["name"])

        # Каждая категория представлена хотя бы одним устройством
        used_types = {d["type"] for d in example.DEVICES}
        self.assertEqual(used_types, set(example.CATEGORIES))

        # И хотя бы один светильник с таймером — иначе пример не показывает главную функцию
        lights = [d for d in example.DEVICES if d["type"] == "lights"]
        self.assertTrue(any(d.get("timer_minutes") for d in lights))


if __name__ == "__main__":
    unittest.main()
