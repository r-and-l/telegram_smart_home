#!/usr/bin/env python3
"""
Поиск дешёвых авиабилетов в Хошимин через Aviasales (Travelpayouts) Data API.

Установка:   pip install -r requirements.txt
Токен:       бесплатно на https://www.travelpayouts.com (раздел «Инструменты» -> API)
Запуск:      export TP_TOKEN="ваш_токен"
             python flight_finder.py
Раз в N часов (cron):   0 */6 * * * TP_TOKEN=xxx python /путь/flight_finder.py

Опционально Telegram-уведомления: TG_BOT_TOKEN и TG_CHAT_ID.
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

try:
    import requests
except ImportError:
    requests = None

# ===================== НАСТРОЙКИ =====================
ORIGINS = ["GOJ", "MOW"]          # GOJ = Нижний Новгород, MOW = все аэропорты Москвы
DESTINATION = "SGN"               # Хошимин

DEPART_FROM = date(2027, 1, 25)   # окно вылета туда
DEPART_TO = date(2027, 2, 5)
STAY_MIN_DAYS = 27                # длительность поездки (мин/макс), дней
STAY_MAX_DAYS = 33

MAX_PRICE = 60000                 # бюджет на человека, руб (туда-обратно)
MAX_TRANSFERS = 1                 # максимум пересадок
MAX_DURATION_HOURS = 24           # максимум времени в пути в одну сторону (с пересадкой)
TOP_N = 15                        # сколько лучших вариантов показать

CURRENCY = "rub"
CSV_FILE = "flights_found.csv"
# ======================================================

API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
TOKEN = os.getenv("TP_TOKEN")


def _http_get_json(url: str, params: dict, timeout: int = 20) -> dict:
    """Выполняет GET-запрос через requests (или urllib.request, если requests не установлен)."""
    if requests is not None:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{query}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch(
    origin: str,
    depart_month: str,
    return_month: str,
    token: str | None = None,
    destination: str = DESTINATION,
    currency: str = CURRENCY,
) -> list[dict]:
    """Запрос цен на месяц вылета и месяц возврата."""
    active_token = token if token is not None else TOKEN
    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": depart_month,   # формат YYYY-MM
        "return_at": return_month,
        "unique": "false",
        "sorting": "price",
        "cur": currency,
        "limit": 1000,
        "one_way": "false",
        "token": active_token,
    }
    for attempt in range(3):
        try:
            data = _http_get_json(API_URL, params=params, timeout=20)
            if not data.get("success", True):
                print(f"[!] API вернул ошибку: {data}", file=sys.stderr)
                return []
            return data.get("data", [])
        except Exception as e:
            print(f"[!] {origin} {depart_month}->{return_month}, попытка {attempt + 1}: {e}",
                  file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return []


def months_between(d1: date, d2: date) -> list[str]:
    """Список месяцев вида YYYY-MM между двумя датами включительно."""
    result, cur = [], date(d1.year, d1.month, 1)
    while cur <= d2:
        result.append(cur.strftime("%Y-%m"))
        cur = date(cur.year + (cur.month // 12), cur.month % 12 + 1, 1)
    return result


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)


def _as_date(val) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val))


def collect(
    token: str | None = None,
    origins: list[str] | None = None,
    destination: str = DESTINATION,
    depart_from: date | str = DEPART_FROM,
    depart_to: date | str = DEPART_TO,
    stay_min_days: int = STAY_MIN_DAYS,
    stay_max_days: int = STAY_MAX_DAYS,
    max_price: int = MAX_PRICE,
    max_transfers: int = MAX_TRANSFERS,
    max_duration_hours: float = MAX_DURATION_HOURS,
    currency: str = CURRENCY,
    delay: float = 0.3,
) -> list[dict]:
    active_origins = origins if origins is not None else ORIGINS
    dep_from = _as_date(depart_from)
    dep_to = _as_date(depart_to)

    depart_months = months_between(dep_from, dep_to)
    return_months = months_between(
        dep_from + timedelta(days=stay_min_days),
        dep_to + timedelta(days=stay_max_days),
    )

    seen, results = set(), []
    for origin in active_origins:
        for dm in depart_months:
            for rm in return_months:
                for t in fetch(
                    origin,
                    dm,
                    rm,
                    token=token,
                    destination=destination,
                    currency=currency,
                ):
                    try:
                        dep = parse_dt(t["departure_at"])
                        ret = parse_dt(t["return_at"])
                    except (KeyError, ValueError):
                        continue

                    stay = (ret.date() - dep.date()).days
                    if not (dep_from <= dep.date() <= dep_to):
                        continue
                    if not (stay_min_days <= stay <= stay_max_days):
                        continue
                    if t.get("price", 10**9) > max_price:
                        continue

                    transfers_to = t.get("transfers", 0)
                    transfers_back = t.get("return_transfers", 0)
                    if max(transfers_to, transfers_back) > max_transfers:
                        continue

                    dur_to = t.get("duration_to", 0) / 60   # минуты -> часы
                    dur_back = t.get("duration_back", 0) / 60
                    if max(dur_to, dur_back) > max_duration_hours:
                        continue

                    key = (origin, t["departure_at"], t["return_at"], t["price"], t.get("airline"))
                    if key in seen:
                        continue
                    seen.add(key)

                    results.append({
                        "origin": origin,
                        "destination": destination,
                        "price": t["price"],
                        "airline": t.get("airline", ""),
                        "depart": dep.strftime("%Y-%m-%d %H:%M"),
                        "return": ret.strftime("%Y-%m-%d %H:%M"),
                        "stay_days": stay,
                        "transfers_to": transfers_to,
                        "transfers_back": transfers_back,
                        "hours_to": round(dur_to, 1),
                        "hours_back": round(dur_back, 1),
                        "link": "https://www.aviasales.ru" + t["link"] if t.get("link") else "",
                    })
                if delay > 0:
                    time.sleep(delay)  # не долбим API

    # сортировка: сначала цена, при равной цене — меньше времени в пути
    results.sort(key=lambda x: (x["price"], x["hours_to"] + x["hours_back"]))
    return results


def save_csv(rows: list[dict], csv_file: str = CSV_FILE) -> None:
    if not rows:
        return
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("Под ваши условия билетов не найдено. Ослабьте фильтры (MAX_PRICE, MAX_TRANSFERS, даты).")
        return
    print(f"\nНайдено вариантов: {len(rows)}. Лучшие {min(TOP_N, len(rows))}:\n")
    print(f"{'Цена':>8} | {'Из':3} | {'Авиакомп.':9} | {'Туда':16} | {'Обратно':16} | "
          f"{'Дней':>4} | {'Перес.':6} | {'Часов':9}")
    print("-" * 95)
    for r in rows[:TOP_N]:
        print(f"{r['price']:>8} | {r['origin']:3} | {r['airline']:9} | {r['depart']:16} | "
              f"{r['return']:16} | {r['stay_days']:>4} | "
              f"{r['transfers_to']}/{r['transfers_back']:<4} | {r['hours_to']}/{r['hours_back']}")
    print("\nСсылка на лучший вариант:\n", rows[0]["link"])


def notify_telegram(rows: list[dict]) -> None:
    bot, chat = os.getenv("TG_BOT_TOKEN"), os.getenv("TG_CHAT_ID")
    if not (bot and chat and rows):
        return
    best = rows[0]
    text = (f"✈️ Лучший билет в Хошимин: {best['price']} ₽\n"
            f"{best['origin']} → SGN, {best['airline']}\n"
            f"Туда: {best['depart']}\nОбратно: {best['return']}\n"
            f"Пересадок: {best['transfers_to']}/{best['transfers_back']}\n{best['link']}")
    try:
        if requests is not None:
            requests.post(f"https://api.telegram.org/bot{bot}/sendMessage",
                          data={"chat_id": chat, "text": text}, timeout=15)
        else:
            payload = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode("utf-8")
            urllib.request.urlopen(f"https://api.telegram.org/bot{bot}/sendMessage", data=payload, timeout=15)
    except Exception as e:
        print(f"[!] Telegram: {e}", file=sys.stderr)


def main() -> None:
    if not TOKEN:
        sys.exit("Задайте токен: export TP_TOKEN='ваш_токен' (получить на travelpayouts.com)")
    rows = collect()
    print_table(rows)
    save_csv(rows)
    notify_telegram(rows)
    if rows:
        print(f"\nВсе результаты сохранены в {CSV_FILE}")


if __name__ == "__main__":
    main()
