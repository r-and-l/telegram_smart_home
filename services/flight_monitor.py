import os
import threading
from datetime import datetime
from html import escape

from config import FLIGHT_CONFIG
from flight_finder import flight_finder


class FlightMonitor:
    """
    Сервис поиска авиабилетов (Aviasales / Travelpayouts) с ежедневным расписанием
    и управлением из меню Telegram.
    """

    _MIN_PRICE = 10000
    _MAX_PRICE = 500000

    def __init__(self, app, telegram_api, store=None, on_update=None):
        self.app = app
        self.telegram = telegram_api
        self.store = store or telegram_api.store
        self.on_update = on_update
        self.is_searching = False
        self._lock = threading.Lock()

        saved = self.store.get("flight_monitor", {})
        if not isinstance(saved, dict):
            saved = {}

        self.enabled = bool(saved.get("enabled", FLIGHT_CONFIG.get("enabled", True)))
        self.check_time = self._normalize_time(
            saved.get("check_time") or FLIGHT_CONFIG.get("check_time", "10:00")
        )
        self.max_price = int(saved.get("max_price") or FLIGHT_CONFIG.get("max_price", 60000))
        self.last_check = saved.get("last_check")
        self.last_results = saved.get("last_results", [])
        self.last_total = int(saved.get("last_total", len(self.last_results)))
        self.last_error = saved.get("last_error")
        self.last_daily_sent_date = saved.get("last_daily_sent_date")

    # ───────────── Персистентность и настройки ─────────────

    @staticmethod
    def _normalize_time(value):
        try:
            parts = str(value).strip().split(":")
            h = max(0, min(23, int(parts[0])))
            m = max(0, min(59, int(parts[1])))
            return f"{h:02d}:{m:02d}"
        except Exception:
            return "10:00"

    def _save_state(self):
        self.store.set("flight_monitor", {
            "enabled": self.enabled,
            "check_time": self.check_time,
            "max_price": self.max_price,
            "last_check": self.last_check,
            "last_results": self.last_results,
            "last_total": self.last_total,
            "last_error": self.last_error,
            "last_daily_sent_date": self.last_daily_sent_date,
        })

    def get_token(self):
        return (
            FLIGHT_CONFIG.get("tp_token")
            or os.getenv("TP_TOKEN")
            or getattr(flight_finder, "TOKEN", None)
            or ""
        ).strip()

    def status_summary(self):
        """Сводка состояния для отрисовки меню в Telegram."""
        return {
            "enabled": self.enabled,
            "check_time": self.check_time,
            "max_price": self.max_price,
            "default_max_price": int(FLIGHT_CONFIG.get("max_price", 60000)),
            "origins": list(FLIGHT_CONFIG.get("origins", ["GOJ", "MOW"])),
            "destination": FLIGHT_CONFIG.get("destination", "SGN"),
            "depart_from": str(FLIGHT_CONFIG.get("depart_from", "2027-01-25")),
            "depart_to": str(FLIGHT_CONFIG.get("depart_to", "2027-02-05")),
            "stay_min_days": int(FLIGHT_CONFIG.get("stay_min_days", 27)),
            "stay_max_days": int(FLIGHT_CONFIG.get("stay_max_days", 33)),
            "max_transfers": int(FLIGHT_CONFIG.get("max_transfers", 1)),
            "max_duration_hours": int(FLIGHT_CONFIG.get("max_duration_hours", 24)),
            "has_token": bool(self.get_token()),
            "is_searching": self.is_searching,
            "last_check": self.last_check,
            "last_results": list(self.last_results),
            "last_total": self.last_total,
            "last_error": self.last_error,
        }

    def toggle_enabled(self):
        self.enabled = not self.enabled
        self._save_state()
        self.app.log(f"[FLIGHTS] Daily check {'enabled' if self.enabled else 'disabled'} ({self.check_time})")

    def set_check_time(self, hh_mm):
        normalized = self._normalize_time(hh_mm)
        self.check_time = normalized
        now_hm = datetime.now().strftime("%H:%M")
        # Если новое время сегодня ещё не наступило, разрешаем сработать сегодня
        if normalized > now_hm and self.last_daily_sent_date == datetime.now().strftime("%Y-%m-%d"):
            self.last_daily_sent_date = None
        self._save_state()
        self.app.log(f"[FLIGHTS] Daily check time set to {self.check_time}")

    def adjust_check_time(self, delta_minutes):
        h, m = (int(x) for x in self.check_time.split(":"))
        total = (h * 60 + m + int(delta_minutes)) % (24 * 60)
        new_h, new_m = divmod(total, 60)
        self.set_check_time(f"{new_h:02d}:{new_m:02d}")

    def adjust_max_price(self, delta_rub):
        self.max_price = max(
            self._MIN_PRICE,
            min(self._MAX_PRICE, self.max_price + int(delta_rub))
        )
        self._save_state()
        self.app.log(f"[FLIGHTS] Max price set to {self.max_price}")

    def reset_settings(self):
        self.enabled = bool(FLIGHT_CONFIG.get("enabled", True))
        self.check_time = self._normalize_time(FLIGHT_CONFIG.get("check_time", "10:00"))
        self.max_price = int(FLIGHT_CONFIG.get("max_price", 60000))
        self._save_state()
        self.app.log("[FLIGHTS] Settings reset to defaults from FLIGHT_CONFIG")

    # ───────────── Поиск и уведомления ─────────────

    def tick(self, kwargs=None):
        """Вызывается раз в минуту из AppDaemon: проверяет, не пора ли выполнить ежедневный поиск."""
        if not self.enabled or self.is_searching:
            return
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        now_hm = now.strftime("%H:%M")
        if now_hm == self.check_time and self.last_daily_sent_date != today_str:
            self.last_daily_sent_date = today_str
            self._save_state()
            self.app.log(f"[FLIGHTS] Starting scheduled daily flight check at {now_hm}")
            self.run_search(send_report=True, async_run=True)

    def run_search(self, send_report=True, async_run=False):
        """Запускает поиск билетов (синхронно или в фоновом потоке)."""
        if self.is_searching:
            return None
        if async_run:
            thread = threading.Thread(
                target=self._execute_search,
                kwargs={"send_report": send_report},
                daemon=True,
            )
            thread.start()
            return None
        return self._execute_search(send_report=send_report)

    def _execute_search(self, send_report=True):
        with self._lock:
            if self.is_searching:
                return None
            self.is_searching = True

        if self.on_update:
            try:
                self.on_update()
            except Exception:
                pass

        try:
            token = self.get_token()
            now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
            if not token:
                self.last_check = now_str
                self.last_error = "Не задан токен Travelpayouts (tp_token в config.py)"
                self._save_state()
                self.app.log(f"[FLIGHTS] Search skipped: {self.last_error}")
                if send_report:
                    self.telegram.send_notification(
                        "⚠️ <b>Поиск авиабилетов</b>\n\n"
                        "Не задан токен Travelpayouts API.\n"
                        "Укажите <code>tp_token</code> в <code>FLIGHT_CONFIG</code> (<code>config.py</code>) "
                        "или переменную окружения <code>TP_TOKEN</code>."
                    )
                return []

            top_n = int(FLIGHT_CONFIG.get("top_n", 5))
            rows = flight_finder.collect(
                token=token,
                origins=list(FLIGHT_CONFIG.get("origins", ["GOJ", "MOW"])),
                destination=FLIGHT_CONFIG.get("destination", "SGN"),
                depart_from=FLIGHT_CONFIG.get("depart_from", "2027-01-25"),
                depart_to=FLIGHT_CONFIG.get("depart_to", "2027-02-05"),
                stay_min_days=int(FLIGHT_CONFIG.get("stay_min_days", 27)),
                stay_max_days=int(FLIGHT_CONFIG.get("stay_max_days", 33)),
                max_price=self.max_price,
                max_transfers=int(FLIGHT_CONFIG.get("max_transfers", 1)),
                max_duration_hours=float(FLIGHT_CONFIG.get("max_duration_hours", 24)),
                currency=FLIGHT_CONFIG.get("currency", "rub"),
                delay=0.15,
            )

            csv_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "flight_finder",
                "flights_found.csv",
            )
            try:
                flight_finder.save_csv(rows, csv_file=csv_path)
            except Exception as e:
                self.app.log(f"[FLIGHTS] CSV save warning: {e}")

            self.last_check = now_str
            self.last_total = len(rows)
            self.last_results = rows[:top_n]
            self.last_error = None
            self._save_state()

            self.app.log(f"[FLIGHTS] Search complete: found {len(rows)} flights")

            if send_report:
                report_text = self.format_report_message()
                self.telegram.send_notification(report_text, parse_mode="html")

            return rows
        except Exception as e:
            self.last_check = datetime.now().strftime("%d.%m.%Y %H:%M")
            self.last_error = str(e)
            self._save_state()
            self.app.log(f"[FLIGHTS] Search failed: {e}")
            if send_report:
                self.telegram.send_notification(
                    f"⚠️ <b>Ошибка поиска авиабилетов:</b>\n<code>{escape(str(e))}</code>",
                    parse_mode="html",
                )
            return []
        finally:
            self.is_searching = False
            if self.on_update:
                try:
                    self.on_update()
                except Exception:
                    pass

    def format_report_message(self):
        """Форматирует сообщение с результатами ежедневного/ручного поиска для Telegram."""
        s = self.status_summary()
        origins_str = ", ".join(s["origins"])
        dest = s["destination"]
        header = (
            f"✈️ <b>Авиабилеты {escape(origins_str)} → {escape(dest)}</b>\n"
            f"📅 Вылет: {escape(s['depart_from'])} — {escape(s['depart_to'])} "
            f"({s['stay_min_days']}–{s['stay_max_days']} дн.)\n"
            f"💰 Бюджет: до {s['max_price']:,} ₽".replace(",", " ")
        )

        if not self.last_results:
            return (
                f"{header}\n\n"
                "😔 Под заданные условия билетов не найдено.\n"
                "Попробуйте увеличить бюджет в меню «✈️ Билеты»."
            )

        lines = [
            header,
            f"\nНайдено вариантов: <b>{self.last_total}</b>. Лучшие {len(self.last_results)}:\n",
        ]
        for idx, r in enumerate(self.last_results, start=1):
            price_fmt = f"{int(r['price']):,}".replace(",", " ")
            link = r.get("link") or ""
            link_html = f' · <a href="{escape(link)}">Открыть</a>' if link else ""
            lines.append(
                f"{idx}. <b>{price_fmt} ₽</b> | {escape(str(r['origin']))} → {escape(dest)} "
                f"({escape(str(r.get('airline', '—')))})\n"
                f"   🛫 {escape(str(r['depart']))} → 🛬 {escape(str(r['return']))} ({r['stay_days']} дн.)\n"
                f"   🔄 Пересадок: {r['transfers_to']}/{r['transfers_back']} · "
                f"⏱ В пути: {r['hours_to']}/{r['hours_back']} ч{link_html}"
            )
        return "\n".join(lines)
