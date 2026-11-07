import os
import threading
from datetime import date, datetime, timedelta
from html import escape

from config import FLIGHT_CONFIG
from flight_finder import flight_finder
from ui import rich_views


class FlightMonitor:
    """
    Сервис поиска авиабилетов (Aviasales / Travelpayouts + прямые ссылки на Trip.com)
    с поддержкой нескольких городов вылета и назначения, настройкой дат, бюджета
    и ежедневного расписания из меню Telegram.
    """

    _MIN_PRICE = 10000
    _MAX_PRICE = 500000
    _MIN_STAY = 1
    _MAX_STAY = 180

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

        default_origins = list(FLIGHT_CONFIG.get("origins", ["GOJ", "MOW"]))
        saved_origins = saved.get("origins")
        if isinstance(saved_origins, list) and saved_origins:
            self.origins = [str(o).upper().strip() for o in saved_origins if o]
        else:
            self.origins = default_origins

        cfg_dests = FLIGHT_CONFIG.get("destinations") or (
            [FLIGHT_CONFIG["destination"]] if FLIGHT_CONFIG.get("destination") else ["SGN", "DAD"]
        )
        saved_dests = saved.get("destinations")
        if isinstance(saved_dests, list) and saved_dests:
            self.destinations = [str(d).upper().strip() for d in saved_dests if d]
        elif saved.get("destination"):
            self.destinations = [str(saved["destination"]).upper().strip()]
        else:
            self.destinations = [str(d).upper().strip() for d in cfg_dests if d]

        self.depart_from = self._normalize_date(
            saved.get("depart_from") or FLIGHT_CONFIG.get("depart_from", "2027-01-25"),
            fallback="2027-01-25",
        )
        self.depart_to = self._normalize_date(
            saved.get("depart_to") or FLIGHT_CONFIG.get("depart_to", "2027-02-05"),
            fallback="2027-02-05",
        )
        if self.depart_to < self.depart_from:
            self.depart_to = self.depart_from

        self.stay_min_days = max(
            self._MIN_STAY,
            int(saved.get("stay_min_days") or FLIGHT_CONFIG.get("stay_min_days", 27)),
        )
        self.stay_max_days = max(
            self.stay_min_days,
            int(saved.get("stay_max_days") or FLIGHT_CONFIG.get("stay_max_days", 33)),
        )

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

    @property
    def destination(self):
        return self.destinations[0] if self.destinations else "SGN"

    # ───────────── Персистентность и валидация ─────────────

    @staticmethod
    def _normalize_time(value):
        try:
            parts = str(value).strip().split(":")
            h = max(0, min(23, int(parts[0])))
            m = max(0, min(59, int(parts[1])))
            return f"{h:02d}:{m:02d}"
        except Exception:
            return "10:00"

    @staticmethod
    def _normalize_date(value, fallback="2027-01-25"):
        try:
            if isinstance(value, datetime):
                return value.date().isoformat()
            if isinstance(value, date):
                return value.isoformat()
            return date.fromisoformat(str(value).strip()).isoformat()
        except Exception:
            return fallback

    def _save_state(self):
        self.store.set("flight_monitor", {
            "origins": self.origins,
            "destinations": self.destinations,
            "destination": self.destination,
            "depart_from": self.depart_from,
            "depart_to": self.depart_to,
            "stay_min_days": self.stay_min_days,
            "stay_max_days": self.stay_max_days,
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

    def origin_options(self):
        opts = dict(getattr(flight_finder, "ORIGIN_AIRPORTS", {}))
        cfg_opts = FLIGHT_CONFIG.get("origin_options")
        if isinstance(cfg_opts, dict):
            opts.update(cfg_opts)
        for code in self.origins:
            opts.setdefault(code, code)
        return opts

    def destination_options(self):
        opts = dict(getattr(flight_finder, "DESTINATION_AIRPORTS", {}))
        cfg_opts = FLIGHT_CONFIG.get("destination_options")
        if isinstance(cfg_opts, dict):
            opts.update(cfg_opts)
        for code in self.destinations:
            opts.setdefault(code, code)
        return opts

    def city_name(self, code):
        code = str(code).upper().strip()
        return (
            self.origin_options().get(code)
            or self.destination_options().get(code)
            or code
        )

    def status_summary(self):
        """Сводка состояния для отрисовки меню и табличного отчёта в Telegram."""
        dest_labels = [f"{self.city_name(c)} ({c})" for c in self.destinations]
        return {
            "enabled": self.enabled,
            "check_time": self.check_time,
            "max_price": self.max_price,
            "default_max_price": int(FLIGHT_CONFIG.get("max_price", 60000)),
            "origins": list(self.origins),
            "origins_labels": [f"{self.city_name(c)} ({c})" for c in self.origins],
            "destinations": list(self.destinations),
            "destinations_labels": dest_labels,
            "destination": self.destination,
            "destination_label": ", ".join(dest_labels),
            "origin_options": self.origin_options(),
            "destination_options": self.destination_options(),
            "depart_from": self.depart_from,
            "depart_to": self.depart_to,
            "stay_min_days": self.stay_min_days,
            "stay_max_days": self.stay_max_days,
            "max_transfers": int(FLIGHT_CONFIG.get("max_transfers", 1)),
            "max_duration_hours": int(FLIGHT_CONFIG.get("max_duration_hours", 24)),
            "has_token": bool(self.get_token()),
            "is_searching": self.is_searching,
            "last_check": self.last_check,
            "last_results": list(self.last_results),
            "last_total": self.last_total,
            "last_error": self.last_error,
        }

    # ───────────── Настройка маршрута (Откуда / Куда — мультивыбор) ─────────────

    def toggle_origin(self, code):
        """Включает или выключает аэропорт вылета (оставляя минимум один выбранный)."""
        code = str(code).upper().strip()
        if not code:
            return
        if code in self.origins:
            if len(self.origins) > 1:
                self.origins = [o for o in self.origins if o != code]
        else:
            self.origins.append(code)
        self._save_state()
        self.app.log(f"[FLIGHTS] Origins updated: {self.origins}")

    def set_origins(self, codes):
        cleaned = [str(c).upper().strip() for c in codes if c and str(c).strip()]
        if cleaned:
            self.origins = cleaned
            self._save_state()
            self.app.log(f"[FLIGHTS] Origins set to: {self.origins}")

    def toggle_destination(self, code):
        """Включает или выключает аэропорт назначения (оставляя минимум один выбранный)."""
        code = str(code).upper().strip()
        if not code:
            return
        if code in self.destinations:
            if len(self.destinations) > 1:
                self.destinations = [d for d in self.destinations if d != code]
        else:
            self.destinations.append(code)
        self._save_state()
        self.app.log(f"[FLIGHTS] Destinations updated: {self.destinations}")

    def set_destinations(self, codes):
        cleaned = [str(c).upper().strip() for c in codes if c and str(c).strip()]
        if cleaned:
            self.destinations = cleaned
            self._save_state()
            self.app.log(f"[FLIGHTS] Destinations set to: {self.destinations}")

    def set_destination(self, code):
        code = str(code).upper().strip()
        if not code:
            return
        self.destinations = [code]
        self._save_state()
        self.app.log(f"[FLIGHTS] Destination set to: {self.destinations}")

    # ───────────── Настройка дат и длительности ─────────────

    def shift_depart_from(self, delta_days):
        d_from = date.fromisoformat(self.depart_from) + timedelta(days=int(delta_days))
        d_to = date.fromisoformat(self.depart_to)
        if d_from > d_to:
            d_to = d_from
        self.depart_from = d_from.isoformat()
        self.depart_to = d_to.isoformat()
        self._save_state()
        self.app.log(f"[FLIGHTS] Departure window updated: {self.depart_from} .. {self.depart_to}")

    def shift_depart_to(self, delta_days):
        d_from = date.fromisoformat(self.depart_from)
        d_to = date.fromisoformat(self.depart_to) + timedelta(days=int(delta_days))
        if d_to < d_from:
            d_to = d_from
        self.depart_to = d_to.isoformat()
        self._save_state()
        self.app.log(f"[FLIGHTS] Departure window updated: {self.depart_from} .. {self.depart_to}")

    def shift_window(self, delta_days):
        """Сдвигает всё окно вылета (начало и конец) на delta_days дней."""
        delta = timedelta(days=int(delta_days))
        d_from = date.fromisoformat(self.depart_from) + delta
        d_to = date.fromisoformat(self.depart_to) + delta
        self.depart_from = d_from.isoformat()
        self.depart_to = d_to.isoformat()
        self._save_state()
        self.app.log(f"[FLIGHTS] Window shifted: {self.depart_from} .. {self.depart_to}")

    def set_window_span(self, span_days):
        """Задаёт ширину окна вылета от depart_from (например, 7, 14, 30 дней)."""
        d_from = date.fromisoformat(self.depart_from)
        d_to = d_from + timedelta(days=max(0, int(span_days)))
        self.depart_to = d_to.isoformat()
        self._save_state()
        self.app.log(f"[FLIGHTS] Window span set ({span_days}d): {self.depart_from} .. {self.depart_to}")

    def set_stay_range(self, min_days, max_days):
        mn = max(self._MIN_STAY, min(self._MAX_STAY, int(min_days)))
        mx = max(mn, min(self._MAX_STAY, int(max_days)))
        self.stay_min_days = mn
        self.stay_max_days = mx
        self._save_state()
        self.app.log(f"[FLIGHTS] Stay duration set: {self.stay_min_days}..{self.stay_max_days} days")

    def shift_stay_range(self, delta_days):
        delta = int(delta_days)
        span = max(0, self.stay_max_days - self.stay_min_days)
        new_min = max(self._MIN_STAY, min(self._MAX_STAY - span, self.stay_min_days + delta))
        new_max = min(self._MAX_STAY, new_min + span)
        self.set_stay_range(new_min, new_max)

    # ───────────── Настройка расписания и бюджета ─────────────

    def toggle_enabled(self):
        self.enabled = not self.enabled
        self._save_state()
        self.app.log(f"[FLIGHTS] Daily check {'enabled' if self.enabled else 'disabled'} ({self.check_time})")

    def set_check_time(self, hh_mm):
        normalized = self._normalize_time(hh_mm)
        self.check_time = normalized
        now_hm = datetime.now().strftime("%H:%M")
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
        self.origins = list(FLIGHT_CONFIG.get("origins", ["GOJ", "MOW"]))
        cfg_dests = FLIGHT_CONFIG.get("destinations") or (
            [FLIGHT_CONFIG["destination"]] if FLIGHT_CONFIG.get("destination") else ["SGN", "DAD"]
        )
        self.destinations = [str(d).upper().strip() for d in cfg_dests if d]
        self.depart_from = self._normalize_date(FLIGHT_CONFIG.get("depart_from", "2027-01-25"))
        self.depart_to = self._normalize_date(FLIGHT_CONFIG.get("depart_to", "2027-02-05"))
        self.stay_min_days = int(FLIGHT_CONFIG.get("stay_min_days", 27))
        self.stay_max_days = int(FLIGHT_CONFIG.get("stay_max_days", 33))
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
                origins=list(self.origins),
                destinations=list(self.destinations),
                depart_from=self.depart_from,
                depart_to=self.depart_to,
                stay_min_days=self.stay_min_days,
                stay_max_days=self.stay_max_days,
                max_price=self.max_price,
                max_transfers=int(FLIGHT_CONFIG.get("max_transfers", 1)),
                max_duration_hours=float(FLIGHT_CONFIG.get("max_duration_hours", 24)),
                currency=FLIGHT_CONFIG.get("currency", "rub"),
                delay=0.15,
            )

            # Гарантируем наличие trip_link для каждого результата
            currency = FLIGHT_CONFIG.get("currency", "rub")
            for r in rows:
                if not r.get("trip_link"):
                    r["trip_link"] = flight_finder.build_trip_link(
                        r.get("origin", ""),
                        r.get("destination", self.destination),
                        r.get("depart", ""),
                        r.get("return", ""),
                        currency=currency,
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
                summary = self.status_summary()
                report_text = self.format_report_message(summary)
                report_rich_html = rich_views.render_flights_report_html(summary)
                try:
                    self.telegram.send_notification(
                        report_text,
                        parse_mode="html",
                        rich_html=report_rich_html,
                    )
                except TypeError:
                    # Для тестовых заглушек send_notification без rich_html
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

    def format_report_message(self, summary=None):
        """Форматирует табличный отчёт (fallback для обычного HTML с моноширинной таблицей и ссылками)."""
        s = summary or self.status_summary()
        origins_str = ", ".join(s["origins"])
        dests_str = ", ".join(s["destinations"])
        header = (
            f"✈️ <b>Авиабилеты: {escape(origins_str)} → {escape(dests_str)}</b>\n"
            f"📅 Вылет: {escape(s['depart_from'])} — {escape(s['depart_to'])} "
            f"({s['stay_min_days']}–{s['stay_max_days']} дн.) | "
            f"💰 до {s['max_price']:,} ₽".replace(",", " ")
        )

        if not self.last_results:
            return (
                f"{header}\n\n"
                "😔 Под заданные условия билетов не найдено.\n"
                "Попробуйте изменить даты или бюджет в меню «✈️ Билеты»."
            )

        table_lines = [
            f"{'#':<2} {'Цена':>7} | {'Рейс':<7} | {'Туда':<10} | {'Обр.':<10} | {'Дн':>2} | {'Пер':<3}",
            "-" * 54,
        ]
        link_lines = []

        for idx, r in enumerate(self.last_results, start=1):
            price_fmt = f"{int(r['price']):,}".replace(",", " ")
            r_dest = r.get("destination", self.destination)
            route = f"{r['origin']}→{r_dest}"
            dep_short = str(r.get("depart", ""))[:10]
            ret_short = str(r.get("return", ""))[:10]
            transfers = f"{r['transfers_to']}/{r['transfers_back']}"
            table_lines.append(
                f"{idx:<2} {price_fmt:>7} | {route:<7} | {dep_short:<10} | {ret_short:<10} | "
                f"{r['stay_days']:>2} | {transfers:<3}"
            )

            links = []
            if r.get("link"):
                links.append(f'<a href="{escape(r["link"])}">Aviasales</a>')
            if r.get("trip_link"):
                links.append(f'<a href="{escape(r["trip_link"])}">Trip.com</a>')
            if links:
                link_lines.append(
                    f"{idx}. <b>{price_fmt} ₽</b> ({escape(route)}, {escape(str(r.get('airline', '—')))}): "
                    + " · ".join(links)
                )

        pre_block = "<pre>" + escape("\n".join(table_lines)) + "</pre>"
        parts = [
            header,
            f"Найдено вариантов: <b>{self.last_total}</b> (показаны топ-{len(self.last_results)}):",
            pre_block,
        ]
        if link_lines:
            parts.append("🔗 <b>Ссылки для покупки:</b>\n" + "\n".join(link_lines))
        return "\n\n".join(parts)
