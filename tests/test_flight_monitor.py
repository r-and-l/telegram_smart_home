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

    def send_notification(self, text, inline_keyboard=None, parse_mode="html",
                          rich_html=None, rich_blocks=None):
        self.notifications.append((text, inline_keyboard, parse_mode, rich_html))
        return len(self.notifications)

    def delete_notification(self, message_id):
        return True


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
        notif_rich = self.tg.notifications[0][3]
        self.assertIn("48 500", notif_text)
        self.assertIn("<pre>", notif_text)
        self.assertIn("Trip.com", notif_text)
        self.assertIn("<table bordered striped compact>", notif_rich)
        self.assertIn("Trip.com", notif_rich)
        self.assertIn("https://www.aviasales.ru/search/MOW2801SGN25021", notif_rich)

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

    def test_route_and_date_customization_via_callbacks(self):
        lm = LightMonitor(self.app, self.tg, store=self.store)
        fm = FlightMonitor(self.app, self.tg, store=self.store)
        mm = MenuManager(self.app, self.tg, light_monitor=lm, flight_monitor=fm)
        auto = Automations(self.app, self.tg, mm)
        router = Router(self.app, mm, lm, auto, self.tg, flight_monitor=fm)

        # Переход в подменю городов вылета и добавление LED
        router.inline_callback("telegram_callback", {"command": "/menu:flights_origins", "chat_id": 12345}, {})
        self.assertEqual(mm.current_menu, "flights_origins")
        router.inline_callback("telegram_callback", {"command": "/flights:origin:LED", "chat_id": 12345}, {})
        self.assertIn("LED", fm.origins)

        # Переход в подменю назначения и мультивыбор (SGN, DAD + добавление BKK)
        router.inline_callback("telegram_callback", {"command": "/menu:flights_dest", "chat_id": 12345}, {})
        router.inline_callback("telegram_callback", {"command": "/flights:dest:BKK", "chat_id": 12345}, {})
        self.assertIn("SGN", fm.destinations)
        self.assertIn("DAD", fm.destinations)
        self.assertIn("BKK", fm.destinations)
        self.assertIn("Бангкок (BKK)", self.tg.rendered[-1]["rich_html"])

        # Переход в подменю дат и сдвиг дат + выбор длительности
        router.inline_callback("telegram_callback", {"command": "/menu:flights_dates", "chat_id": 12345}, {})
        router.inline_callback("telegram_callback", {"command": "/flights:from:7", "chat_id": 12345}, {})
        self.assertEqual(fm.depart_from, "2027-02-01")
        router.inline_callback("telegram_callback", {"command": "/flights:span:14", "chat_id": 12345}, {})
        self.assertEqual(fm.depart_to, "2027-02-15")
        router.inline_callback("telegram_callback", {"command": "/flights:stay:12:16", "chat_id": 12345}, {})
        self.assertEqual((fm.stay_min_days, fm.stay_max_days), (12, 16))

        # Проверяем сохранение в Store
        fm_reloaded = FlightMonitor(self.app, self.tg, store=self.store)
        self.assertIn("LED", fm_reloaded.origins)
        self.assertEqual(fm_reloaded.destinations, ["SGN", "DAD", "BKK"])
        self.assertEqual(fm_reloaded.depart_from, "2027-02-01")
        self.assertEqual(fm_reloaded.depart_to, "2027-02-15")
        self.assertEqual((fm_reloaded.stay_min_days, fm_reloaded.stay_max_days), (12, 16))

    @patch("flight_finder.flight_finder.search_places")
    def test_airport_database_search_via_text_and_buttons(self, mock_search_places):
        mock_search_places.return_value = [
            {"code": "SGN", "name": "Хошимин", "country": "Вьетнам", "label": "Хошимин, Вьетнам"},
            {"code": "DAD", "name": "Дананг", "country": "Вьетнам", "label": "Дананг, Вьетнам"},
            {"code": "PQC", "name": "Фукуок", "country": "Вьетнам", "label": "Фукуок, Вьетнам"},
        ]
        lm = LightMonitor(self.app, self.tg, store=self.store)
        fm = FlightMonitor(self.app, self.tg, store=self.store)
        mm = MenuManager(self.app, self.tg, light_monitor=lm, flight_monitor=fm)
        auto = Automations(self.app, self.tg, mm)
        router = Router(self.app, mm, lm, auto, self.tg, flight_monitor=fm)

        # Открываем меню «Куда» и пишем в чат «вьетнам»
        router.inline_callback("telegram_callback", {"command": "/menu:flights_dest", "chat_id": 12345}, {})
        router.telegram_text("telegram_text", {"text": "вьетнам", "chat_id": 12345, "id": 999}, {})

        mock_search_places.assert_called_with("вьетнам", locale="ru", limit=12)
        self.assertIn("Фукуок, Вьетнам (PQC)", self.tg.rendered[-1]["rich_html"])

        # Выбираем найденный аэропорт Фукуок (PQC)
        router.inline_callback("telegram_callback", {"command": "/flights:dest:PQC", "chat_id": 12345}, {})
        self.assertIn("PQC", fm.destinations)
        self.assertEqual(fm.city_name("PQC"), "Фукуок")

    @patch("flight_finder.flight_finder.collect")
    @patch("flight_finder.flight_finder.save_csv")
    def test_balanced_results_include_all_selected_destinations(self, _mock_csv, mock_collect):
        # 6 дешёвых билетов в SGN и 2 чуть дороже в DAD — оба города должны попасть в таблицу
        sgn_flights = [
            {
                "origin": "MOW",
                "destination": "SGN",
                "price": 48000 + i * 500,
                "airline": "MU",
                "depart": "2027-01-28 19:00",
                "return": "2027-02-25 11:30",
                "stay_days": 28,
                "transfers_to": 1,
                "transfers_back": 1,
                "hours_to": 15.0,
                "hours_back": 16.0,
                "link": "https://www.aviasales.ru/search/1",
            }
            for i in range(6)
        ]
        dad_flights = [
            {
                "origin": "MOW",
                "destination": "DAD",
                "price": 57000 + i * 500,
                "airline": "CZ",
                "depart": "2027-01-29 20:00",
                "return": "2027-02-26 14:00",
                "stay_days": 28,
                "transfers_to": 2,
                "transfers_back": 2,
                "hours_to": 22.0,
                "hours_back": 23.0,
                "link": "https://www.aviasales.ru/search/2",
            }
            for i in range(2)
        ]
        mock_collect.return_value = sgn_flights + dad_flights

        fm = FlightMonitor(self.app, self.tg, store=self.store)
        fm.set_destinations(["SGN", "DAD"])
        with patch.object(fm, "get_token", return_value="test_tp_token"):
            fm.run_search(send_report=False, async_run=False)

        dests_in_table = {r["destination"] for r in fm.last_results}
        self.assertIn("SGN", dests_in_table)
        self.assertIn("DAD", dests_in_table)
        self.assertEqual(fm.last_counts_by_dest, {"SGN": 6, "DAD": 2})

    @patch("flight_finder.flight_finder.search_places")
    def test_in_message_details_accordions_and_keyboard_search(self, mock_search_places):
        from ui.rich_views import render_flights_menu
        mock_search_places.return_value = [
            {"code": "PQC", "name": "Фукуок", "country_name": "Вьетнам", "label": "Фукуок, Вьетнам"},
        ]
        fm = FlightMonitor(self.app, self.tg, store=self.store)

        # 1) Проверяем, что меню назначения рендерит раскрывающиеся <details><summary> аккордеоны стран
        dest_html = render_flights_menu(fm.status_summary(), sub_menu="dest")
        self.assertIn("<details open>", dest_html)
        self.assertIn("<summary><b>🇻🇳 Вьетнам</b>", dest_html)
        self.assertIn("/flights:kch:dest:В", dest_html)

        # 2) Вводим 2 буквы через встроенную в сообщение клавиатуру
        fm.append_search_char("Ф")
        self.assertEqual(fm.place_search_query, "Ф")
        mock_search_places.assert_not_called()

        fm.append_search_char("У")
        self.assertEqual(fm.place_search_query, "ФУ")
        mock_search_places.assert_called_once_with("ФУ", locale="ru", limit=12)
        self.assertEqual(len(fm.place_search_results), 1)

        # 3) Проверяем рендер результатов поиска внутри открытого <details open>
        dest_html_after = render_flights_menu(fm.status_summary(), sub_menu="dest")
        self.assertIn("Найдено в БД Aviasales по запросу «ФУ»", dest_html_after)
        self.assertIn("/flights:dest:PQC", dest_html_after)

        # 4) Backspace до 1 символа очищает результаты
        fm.backspace_search_char()
        self.assertEqual(fm.place_search_query, "Ф")
        self.assertEqual(fm.place_search_results, [])

    @patch("flight_finder.flight_finder.fetch")
    def test_one_way_search_and_trip_link(self, mock_fetch):
        from flight_finder import flight_finder
        from ui.rich_views import render_flights_menu

        mock_fetch.return_value = [
            {
                "departure_at": "2027-01-28T10:00:00Z",
                "price": 24500,
                "airline": "3U",
                "transfers": 1,
                "duration_to": 900,
                "link": "/search/MOW2801DAD1",
            }
        ]
        fm = FlightMonitor(self.app, self.tg, store=self.store)
        fm.set_origins(["MOW"])
        fm.set_destinations(["DAD"])
        fm.set_one_way(True)
        self.assertTrue(fm.one_way)

        with patch.object(fm, "get_token", return_value="test_tp_token"):
            rows = fm.run_search(send_report=False, async_run=False)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["one_way"])
        self.assertEqual(rows[0]["return"], "")
        self.assertEqual(rows[0]["stay_days"], 0)
        self.assertIn("triptype=ow", rows[0]["trip_link"])
        self.assertNotIn("rdate=", rows[0]["trip_link"])

        menu_html = render_flights_menu(fm.status_summary())
        self.assertIn("только туда", menu_html)
        self.assertIn("triptype=ow", menu_html)


if __name__ == "__main__":
    unittest.main()

