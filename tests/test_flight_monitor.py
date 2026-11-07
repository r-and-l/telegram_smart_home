import os
import tempfile
import unittest
from unittest.mock import patch

from core.router import Router
from core.store import Store
from services.automations import Automations
from services.flight_monitor import FlightMonitor
from services.light_monitor import LightMonitor
from services.menu_manager import MenuManager


class FakeApp:
    def __init__(self):
        self.states = {}
        self.services_called = []
        self.logs = []
        self.event_listeners = {}

    def log(self, msg):
        self.logs.append(msg)

    def get_state(self, entity, attribute=None):
        return self.states.get((entity, attribute))

    def listen_state(self, cb, entity, **kwargs):
        pass

    def listen_event(self, cb, event):
        self.event_listeners[event] = cb

    def run_in(self, cb, delay, **kwargs):
        return ("timer", delay)

    def cancel_timer(self, handle):
        pass

    def call_service(self, service, **kwargs):
        self.services_called.append((service, kwargs))


class FakeTelegram:
    def __init__(self, store):
        self.store = store
        self.main_message_id = 100
        self.chat_id = 12345
        self.bot_token = "fake_token"
        self.rendered = []
        self.notifications = []

    def update_chat_id(self, chat_id):
        if chat_id:
            self.chat_id = chat_id

    def reset_message_id(self):
        self.main_message_id = None

    def render_message(self, **kwargs):
        self.rendered.append(kwargs)

    def send_notification(self, text, inline_keyboard=None, parse_mode="html"):
        self.notifications.append((text, inline_keyboard, parse_mode))
        return len(self.notifications)


class TestFlightMonitor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.tmp.close()
        self.app = FakeApp()
        self.store = Store(self.app, path=self.tmp.name)
        self.tg = FakeTelegram(self.store)

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.remove(self.tmp.name)

    def test_schedule_and_budget_controls_persist(self):
        fm = FlightMonitor(self.app, self.tg, store=self.store)
        self.assertTrue(fm.enabled)
        self.assertEqual(fm.check_time, "10:00")

        fm.adjust_check_time(75)  # +1h 15m -> 11:15
        self.assertEqual(fm.check_time, "11:15")

        fm.adjust_max_price(-5000)
        self.assertEqual(fm.max_price, 55000)

        fm.toggle_enabled()
        self.assertFalse(fm.enabled)

        # Проверяем сохранение в Store
        fm2 = FlightMonitor(self.app, self.tg, store=self.store)
        self.assertEqual(fm2.check_time, "11:15")
        self.assertEqual(fm2.max_price, 55000)
        self.assertFalse(fm2.enabled)

    @patch("flight_finder.flight_finder.collect")
    @patch("flight_finder.flight_finder.save_csv")
    def test_search_sends_daily_report(self, _mock_csv, mock_collect):
        mock_collect.return_value = [
            {
                "origin": "MOW",
                "destination": "SGN",
                "price": 48500,
                "airline": "SU",
                "depart": "2027-01-28 19:00",
                "return": "2027-02-25 11:30",
                "stay_days": 28,
                "transfers_to": 0,
                "transfers_back": 0,
                "hours_to": 10.5,
                "hours_back": 11.0,
                "link": "https://www.aviasales.ru/search/MOW2801SGN25021",
            }
        ]
        fm = FlightMonitor(self.app, self.tg, store=self.store)
        with patch.object(fm, "get_token", return_value="test_tp_token"):
            rows = fm.run_search(send_report=True, async_run=False)

        self.assertEqual(len(rows), 1)
        self.assertEqual(fm.last_total, 1)
        self.assertEqual(len(self.tg.notifications), 1)
        notif_text = self.tg.notifications[0][0]
        self.assertIn("48 500 ₽", notif_text)
        self.assertIn("MOW → SGN", notif_text)
        self.assertIn("https://www.aviasales.ru/search/MOW2801SGN25021", notif_text)

    def test_router_opens_flights_menu_and_updates_time(self):
        lm = LightMonitor(self.app, self.tg, store=self.store)
        fm = FlightMonitor(self.app, self.tg, store=self.store)
        mm = MenuManager(self.app, self.tg, light_monitor=lm, flight_monitor=fm)
        auto = Automations(self.app, self.tg, mm)
        router = Router(self.app, mm, lm, auto, self.tg, flight_monitor=fm)

        router.inline_callback("telegram_callback", {"command": "/menu:flights", "chat_id": 12345}, {})
        self.assertEqual(mm.current_menu, "flights")
        self.assertIn("✈️ Авиабилеты", self.tg.rendered[-1]["rich_html"])

        router.inline_callback("telegram_callback", {"command": "/flights:set_time:08:00", "chat_id": 12345}, {})
        self.assertEqual(fm.check_time, "08:00")
        self.assertIn("08:00", self.tg.rendered[-1]["rich_html"])


if __name__ == "__main__":
    unittest.main()
