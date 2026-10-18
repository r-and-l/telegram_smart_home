import unittest
from unittest.mock import MagicMock, patch
import json
import urllib.error

from core.route_optimizer import Route, RouteOptimizer
from core.telegram_api import TelegramAPI


class RouteOptimizerTestCase(unittest.TestCase):

    def test_route_initial_state_and_success(self):
        route = Route(index=0, opener=MagicMock(), label="direct")
        self.assertIsNone(route.latency)
        self.assertTrue(route.is_alive)
        self.assertEqual(route.score, 0.5)

        route.record_success(0.200)
        self.assertEqual(route.latency, 0.200)
        self.assertEqual(route.score, 0.200)
        self.assertTrue(route.is_alive)

        # EMA smoothing
        route.record_success(0.400)
        # 0.200 * 0.7 + 0.400 * 0.3 = 0.140 + 0.120 = 0.260
        self.assertAlmostEqual(route.latency, 0.260, places=3)
        self.assertAlmostEqual(route.score, 0.260, places=3)

    def test_route_failure_and_recovery(self):
        route = Route(index=0, opener=MagicMock(), label="socks5://proxy1")
        route.record_success(0.300)

        route.record_failure("timeout")
        self.assertFalse(route.is_alive)
        self.assertEqual(route.consecutive_fails, 1)
        # score = 0.300 + 10 = 10.300
        self.assertAlmostEqual(route.score, 10.300, places=3)

        # Recovery on next success
        route.record_success(0.250)
        self.assertTrue(route.is_alive)
        self.assertEqual(route.consecutive_fails, 0)
        self.assertLess(route.score, 1.0)

    def test_optimizer_ranking(self):
        r1 = Route(index=0, opener=MagicMock(), label="slow_proxy")
        r1.record_success(0.800)

        r2 = Route(index=1, opener=MagicMock(), label="fast_direct")
        r2.record_success(0.150)

        r3 = Route(index=2, opener=MagicMock(), label="dead_proxy")
        r3.record_failure("timeout")

        optimizer = RouteOptimizer([r1, r2, r3])
        ordered = optimizer.get_ordered_routes()

        self.assertEqual([r.label for r in ordered], ["fast_direct", "slow_proxy", "dead_proxy"])
        self.assertEqual(optimizer.active_route.label, "fast_direct")

    def test_benchmark_runs_get_me_and_sorts(self):
        mock_fast = MagicMock()
        mock_fast.open.return_value.__enter__.return_value.read.return_value = b'{"ok": true}'

        mock_slow = MagicMock()
        mock_slow.open.return_value.__enter__.return_value.read.return_value = b'{"ok": true}'

        mock_dead = MagicMock()
        mock_dead.open.side_effect = TimeoutError("Connection timed out")

        r_fast = Route(index=0, opener=mock_fast, label="direct")
        r_slow = Route(index=1, opener=mock_slow, label="slow")
        r_dead = Route(index=2, opener=mock_dead, label="dead")

        app_mock = MagicMock()
        optimizer = RouteOptimizer([r_fast, r_slow, r_dead], app=app_mock)

        best = optimizer.benchmark(bot_token="test_token", timeout=2)
        self.assertIsNotNone(best)
        self.assertTrue(r_fast.is_alive)
        self.assertTrue(r_slow.is_alive)
        self.assertFalse(r_dead.is_alive)
        self.assertEqual(r_dead.consecutive_fails, 1)
        self.assertTrue(app_mock.log.called)

    def test_telegram_api_uses_fastest_route_and_fails_over(self):
        app_mock = MagicMock()
        store_mock = MagicMock()
        store_mock.get.return_value = None

        with patch("core.telegram_api.TELEGRAM_CONFIG", {
            "bot_token": "fake_token",
            "chat_id": 12345,
            "proxy": ["socks5://192.168.1.1:1080"]
        }):
            api = TelegramAPI(app_mock, store=store_mock)
            self.assertEqual(len(api.route_optimizer.routes), 2)  # 1 proxy + 1 direct

            proxy_route = api.route_optimizer.routes[0]
            direct_route = api.route_optimizer.routes[1]

            # Let proxy fail with timeout, while direct succeeds
            proxy_route.opener.open = MagicMock(side_effect=TimeoutError("Handshake timed out"))

            mock_ok_resp = MagicMock()
            mock_ok_resp.__enter__.return_value.read.return_value = json.dumps({"ok": True, "result": {"message_id": 777}}).encode("utf-8")
            direct_route.opener.open = MagicMock(return_value=mock_ok_resp)

            # Call _tg_api
            res = api._tg_api("sendMessage", {"text": "hello"})
            self.assertIsNotNone(res)
            self.assertTrue(res["ok"])

            # Verify proxy is penalized and direct is ranked first now
            self.assertFalse(proxy_route.is_alive)
            self.assertTrue(direct_route.is_alive)
            self.assertEqual(api.route_optimizer.active_route.label, "direct")


if __name__ == "__main__":
    unittest.main()
