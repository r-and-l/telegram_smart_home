import json
import time
import urllib.request
import urllib.error


class Route:
    """Представляет отдельный сетевой маршрут (прокси или direct)."""

    def __init__(self, index, opener, label):
        self.index = index
        self.opener = opener
        self.label = label
        self.latency = None              # последнее сглаженное время ответа (сек)
        self.last_tested = 0.0           # timestamp последней проверки
        self.consecutive_fails = 0       # число ошибок подряд
        self.last_error = None           # последнее описание ошибки

    @property
    def is_alive(self):
        return self.consecutive_fails == 0

    @property
    def score(self):
        """
        Меньше — лучше.
        Определяет приоритет выбора маршрута.
        Штраф за каждую ошибку подряд: +10 сек.
        Если замера еще нет: 0.5 сек (нейтральный старт).
        """
        base = self.latency if self.latency is not None else 0.5
        return base + (self.consecutive_fails * 10.0)

    def record_success(self, duration):
        """Фиксирует успешный ответ и обновляет EMA (экспоненциальное скользящее среднее)."""
        self.consecutive_fails = 0
        self.last_error = None
        self.last_tested = time.time()
        duration = round(duration, 3)
        if self.latency is None:
            self.latency = duration
        else:
            # 70% вес истории + 30% вес нового замера для плавности
            self.latency = round(self.latency * 0.7 + duration * 0.3, 3)

    def record_failure(self, error=None):
        """Фиксирует сбой маршрута (таймаут, разрыв соединения)."""
        self.consecutive_fails += 1
        self.last_error = str(error) if error else "timeout"
        self.last_tested = time.time()


class RouteOptimizer:
    """
    Управляет выбором оптимального маршрута к Telegram Bot API.
    Замеряет latency (пинг) каждого маршрута и сортирует их по скорости.
    """

    def __init__(self, routes, app=None):
        self.routes = routes
        self.app = app
        self._active_route = self.routes[0] if self.routes else None

    @property
    def active_route(self):
        """Текущий лучший маршрут."""
        ordered = self.get_ordered_routes()
        return ordered[0] if ordered else None

    def get_ordered_routes(self):
        """Возвращает маршруты, отсортированные от самого быстрого к худшему."""
        return sorted(self.routes, key=lambda r: r.score)

    def benchmark(self, bot_token, timeout=4):
        """
        Тестирует все маршруты легким запросом getMe.
        Возвращает лучший маршрут.
        """
        if not bot_token or not self.routes:
            return None

        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TelegramSmartHome-Benchmark/1.0",
                "Accept": "application/json",
            }
        )

        for route in self.routes:
            t0 = time.monotonic()
            try:
                with route.opener.open(req, timeout=timeout) as resp:
                    resp.read()
                    duration = time.monotonic() - t0
                    route.record_success(duration)
            except Exception as e:
                route.record_failure(e)

        ordered = self.get_ordered_routes()
        best = ordered[0] if ordered else None

        if self.app:
            lines = ["[ROUTE] Benchmark results (fastest first):"]
            for idx, r in enumerate(ordered, 1):
                if r.is_alive and r.latency is not None:
                    status = f"{int(r.latency * 1000)}ms"
                else:
                    status = f"DOWN ({r.last_error or 'timeout'})"
                tag = " [BEST]" if idx == 1 and r.is_alive else ""
                lines.append(f"  {idx}. {r.label}: {status}{tag}")
            self.app.log("\n".join(lines))

        return best
