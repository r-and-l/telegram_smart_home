#!/usr/bin/env python3
"""
Поиск дешёвых авиабилетов через Aviasales (Travelpayouts) Data API
с генерацией прямых ссылок на Aviasales и Trip.com.

Установка:   pip install -r requirements.txt
Токен:       бесплатно на https://www.travelpayouts.com (раздел «Инструменты» -> API)
Запуск:      export TP_TOKEN="ваш_токен"
             python flight_finder.py
             python flight_finder.py --origins GOJ MOW --destinations SGN DAD --depart-from 2027-01-25 --depart-to 2027-02-05
             python flight_finder.py --interactive
Раз в N часов (cron):   0 */6 * * * TP_TOKEN=xxx python /путь/flight_finder.py

Опционально Telegram-уведомления: TG_BOT_TOKEN и TG_CHAT_ID.
"""

import argparse
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

# ===================== НАСТРОЙКИ ПО УМОЛЧАНИЮ =====================
ORIGINS = ["GOJ", "MOW"]          # GOJ = Нижний Новгород, MOW = все аэропорты Москвы
DESTINATION = "SGN"               # Хошимин (для обратной совместимости)
DESTINATIONS = ["SGN", "DAD"]     # Хошимин, Дананг (поиск сразу в несколько направлений)

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

ORIGIN_GROUPS = {
    "🇷🇺 Центр и СЗ": {
        "GOJ": "Нижний Новгород",
        "MOW": "Москва",
        "LED": "Санкт-Петербург",
        "KGD": "Калининград",
    },
    "🇷🇺 Поволжье и Юг": {
        "KZN": "Казань",
        "KUF": "Самара",
        "UFA": "Уфа",
        "AER": "Сочи",
        "MRV": "Мин. Воды",
        "VOG": "Волгоград",
    },
    "🇷🇺 Урал и Сибирь": {
        "SVX": "Екатеринбург",
        "OVB": "Новосибирск",
        "PEE": "Пермь",
        "CEK": "Челябинск",
        "TJM": "Тюмень",
        "KJA": "Красноярск",
        "IKT": "Иркутск",
    },
    "🌍 СНГ": {
        "MSQ": "Минск",
        "ALA": "Алматы",
        "NQZ": "Астана",
        "EVN": "Ереван",
        "TBS": "Тбилиси",
        "TAS": "Ташкент",
    },
}

DESTINATION_GROUPS = {
    "🇻🇳 Вьетнам": {
        "SGN": "Хошимин",
        "DAD": "Дананг",
        "CXR": "Нячанг",
        "PQC": "Фукуок",
        "HAN": "Ханой",
        "DLI": "Далат",
        "HPH": "Хайфон",
        "UIH": "Куинён",
    },
    "🇹🇭 Таиланд": {
        "BKK": "Бангкок",
        "HKT": "Пхукет",
        "USM": "Самуй",
        "UTP": "Паттайя",
        "KBV": "Краби",
        "CNX": "Чиангмай",
        "DMK": "Дон-Муанг",
    },
    "🇨🇳 Китай и Гонконг": {
        "SYX": "Санья (Хайнань)",
        "HAK": "Хайкоу (Хайнань)",
        "BJS": "Пекин",
        "SHA": "Шанхай",
        "CAN": "Гуанчжоу",
        "CTU": "Чэнду",
        "HKG": "Гонконг",
    },
    "🇮🇩 Индонезия, Малайзия, Сингапур": {
        "DPS": "Бали",
        "CGK": "Джакарта",
        "KUL": "Куала-Лумпур",
        "LGK": "Лангкави",
        "SIN": "Сингапур",
        "MNL": "Манила",
        "CEB": "Себу",
    },
    "🇹🇷 Турция, ОАЭ, Египет": {
        "IST": "Стамбул",
        "AYT": "Анталья",
        "DLM": "Даламан",
        "BJV": "Бодрум",
        "DXB": "Дубай",
        "AUH": "Абу-Даби",
        "SHJ": "Шарджа",
        "SSH": "Шарм-эль-Шейх",
        "HRG": "Хургада",
    },
    "🇱🇰 Шри-Ланка, Мальдивы, Индия": {
        "CMB": "Коломбо",
        "HRI": "Маттала",
        "MLE": "Мальдивы",
        "GOI": "Гоа",
        "SEZ": "Сейшелы",
        "MRU": "Маврикий",
    },
    "🇯🇵 Япония, Корея, Кавказ": {
        "TYO": "Токио",
        "OSA": "Осака",
        "SEL": "Сеул",
        "PUS": "Пусан",
        "TBS": "Тбилиси",
        "BUS": "Батуми",
        "EVN": "Ереван",
        "GYD": "Баку",
    },
}

ORIGIN_AIRPORTS = {code: name for grp in ORIGIN_GROUPS.values() for code, name in grp.items()}
DESTINATION_AIRPORTS = {code: name for grp in DESTINATION_GROUPS.values() for code, name in grp.items()}
# ==================================================================

API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
AUTOCOMPLETE_URL = "https://autocomplete.travelpayouts.com/places2"
TOKEN = os.getenv("TP_TOKEN")

# Коды городов, где в ценовом кэше Aviasales используется код основного аэропорта
_CITY_TO_AIRPORT_CODE = {
    "NHA": "CXR",  # Нячанг -> аэропорт Камрань (CXR)
}


def search_places(query: str, locale: str = "ru", limit: int = 12) -> list[dict]:
    """
    Ищет города и аэропорты в базе Aviasales по названию страны, города или IATA-коду.
    Например, по запросу «Вьетнам» вернёт Хошимин (SGN), Дананг (DAD), Нячанг (CXR),
    Фукуок (PQC), Ханой (HAN), Далат (DLI) и т.д.
    """
    q = str(query or "").strip()
    if not q:
        return []
    params = [
        ("term", q),
        ("locale", locale),
        ("types[]", "city"),
        ("types[]", "airport"),
    ]
    try:
        if requests is not None:
            r = requests.get(AUTOCOMPLETE_URL, params=params, timeout=10)
            r.raise_for_status()
            items = r.json()
        else:
            qs = urllib.parse.urlencode(params)
            req = urllib.request.Request(f"{AUTOCOMPLETE_URL}?{qs}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                items = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[!] Ошибка поиска аэропортов '{q}': {e}", file=sys.stderr)
        return []

    if not isinstance(items, list):
        return []

    seen_codes = set()
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_code = str(item.get("code") or "").upper().strip()
        if not raw_code:
            continue
        code = _CITY_TO_AIRPORT_CODE.get(raw_code, raw_code)
        if code in seen_codes:
            continue
        seen_codes.add(code)

        name = str(item.get("name") or code).strip()
        city_name = str(item.get("city_name") or "").strip()
        country = str(item.get("country_name") or "").strip()
        place_type = item.get("type")

        if place_type == "airport" and city_name and city_name.lower() != name.lower():
            display_name = f"{city_name} · {name}"
        else:
            display_name = name

        label = f"{display_name}, {country}" if country else display_name
        results.append({
            "code": code,
            "name": display_name,
            "country": country,
            "label": label,
        })
        if len(results) >= limit:
            break

    return results


def city_label(iata: str) -> str:
    code = str(iata).upper().strip()
    name = ORIGIN_AIRPORTS.get(code) or DESTINATION_AIRPORTS.get(code)
    return f"{name} ({code})" if name else code


def build_trip_link(
    origin: str,
    destination: str,
    depart_dt_str: str,
    return_dt_str: str,
    currency: str = CURRENCY,
) -> str:
    """Формирует прямую ссылку на поиск этого же перелёта на ru.trip.com."""
    dcity = str(origin).lower().strip()
    acity = str(destination).lower().strip()
    ddate = str(depart_dt_str)[:10]
    rdate = str(return_dt_str)[:10]
    curr = str(currency).upper().strip() or "RUB"
    return (
        f"https://ru.trip.com/flights/showfarefirst?"
        f"dcity={dcity}&acity={acity}&ddate={ddate}&rdate={rdate}"
        f"&triptype=rt&class=y&quantity=1&curr={curr}&locale=ru-RU"
    )


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
            print(f"[!] {origin}->{destination} {depart_month}->{return_month}, попытка {attempt + 1}: {e}",
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
    destination: str | list[str] | None = None,
    destinations: list[str] | None = None,
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
    active_origins = [o.upper().strip() for o in (origins if origins is not None else ORIGINS) if o]

    if destinations is not None:
        raw_dests = destinations
    elif isinstance(destination, (list, tuple)):
        raw_dests = list(destination)
    elif destination:
        raw_dests = [destination]
    else:
        raw_dests = list(DESTINATIONS)
    active_destinations = [str(d).upper().strip() for d in raw_dests if d and str(d).strip()]

    dep_from = _as_date(depart_from)
    dep_to = _as_date(depart_to)
    if dep_to < dep_from:
        dep_to = dep_from

    depart_months = months_between(dep_from, dep_to)
    return_months = months_between(
        dep_from + timedelta(days=stay_min_days),
        dep_to + timedelta(days=stay_max_days),
    )

    seen, results = set(), []
    for origin in active_origins:
        for dest_code in active_destinations:
            for dm in depart_months:
                for rm in return_months:
                    for t in fetch(
                        origin,
                        dm,
                        rm,
                        token=token,
                        destination=dest_code,
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

                        key = (origin, dest_code, t["departure_at"], t["return_at"], t["price"], t.get("airline"))
                        if key in seen:
                            continue
                        seen.add(key)

                        dep_str = dep.strftime("%Y-%m-%d %H:%M")
                        ret_str = ret.strftime("%Y-%m-%d %H:%M")
                        results.append({
                            "origin": origin,
                            "destination": dest_code,
                            "price": t["price"],
                            "airline": t.get("airline", ""),
                            "depart": dep_str,
                            "return": ret_str,
                            "stay_days": stay,
                            "transfers_to": transfers_to,
                            "transfers_back": transfers_back,
                            "hours_to": round(dur_to, 1),
                            "hours_back": round(dur_back, 1),
                            "link": "https://www.aviasales.ru" + t["link"] if t.get("link") else "",
                            "trip_link": build_trip_link(origin, dest_code, dep_str, ret_str, currency),
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


def print_table(rows: list[dict], top_n: int = TOP_N) -> None:
    if not rows:
        print("Под ваши условия билетов не найдено. Ослабьте фильтры (MAX_PRICE, MAX_TRANSFERS, даты).")
        return
    print(f"\nНайдено вариантов: {len(rows)}. Лучшие {min(top_n, len(rows))}:\n")
    print(f"{'Цена':>8} | {'Из':3} | {'Куда':4} | {'Авиакомп.':9} | {'Туда':16} | {'Обратно':16} | "
          f"{'Дней':>4} | {'Перес.':6} | {'Часов':9}")
    print("-" * 102)
    for r in rows[:top_n]:
        dest = r.get("destination", DESTINATION)
        print(f"{r['price']:>8} | {r['origin']:3} | {dest:4} | {r['airline']:9} | {r['depart']:16} | "
              f"{r['return']:16} | {r['stay_days']:>4} | "
              f"{r['transfers_to']}/{r['transfers_back']:<4} | {r['hours_to']}/{r['hours_back']}")
    print("\nСсылки на лучший вариант:")
    print("  Aviasales:", rows[0].get("link", ""))
    print("  Trip.com: ", rows[0].get("trip_link", ""))


def notify_telegram(rows: list[dict], destination: str = DESTINATION) -> None:
    bot, chat = os.getenv("TG_BOT_TOKEN"), os.getenv("TG_CHAT_ID")
    if not (bot and chat and rows):
        return
    best = rows[0]
    dest = best.get("destination", destination)
    text = (f"✈️ Лучший билет ({best['origin']} → {dest}): {best['price']} ₽\n"
            f"Авиакомпания: {best['airline']}\n"
            f"Туда: {best['depart']}\nОбратно: {best['return']} ({best['stay_days']} дн.)\n"
            f"Пересадок: {best['transfers_to']}/{best['transfers_back']}\n"
            f"Aviasales: {best.get('link', '')}\n"
            f"Trip.com: {best.get('trip_link', '')}")
    try:
        if requests is not None:
            requests.post(f"https://api.telegram.org/bot{bot}/sendMessage",
                          data={"chat_id": chat, "text": text}, timeout=15)
        else:
            payload = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode("utf-8")
            urllib.request.urlopen(f"https://api.telegram.org/bot{bot}/sendMessage", data=payload, timeout=15)
    except Exception as e:
        print(f"[!] Telegram: {e}", file=sys.stderr)


def _prompt_interactive(args):
    """Интерактивный ввод параметров в консоли при флаге --interactive."""
    print("=== Настройка поиска авиабилетов ===")
    print("Популярные города вылета:", ", ".join(f"{k} ({v})" for k, v in ORIGIN_AIRPORTS.items()))
    raw_origins = input(f"Города вылета через пробел [{' '.join(args.origins)}]: ").strip()
    if raw_origins:
        args.origins = [x.upper() for x in raw_origins.replace(",", " ").split() if x]

    print("Популярные направления:", ", ".join(f"{k} ({v})" for k, v in DESTINATION_AIRPORTS.items()))
    raw_dest = input(f"Пункты назначения через пробел [{' '.join(args.destinations)}]: ").strip()
    if raw_dest:
        args.destinations = [x.upper() for x in raw_dest.replace(",", " ").split() if x]

    raw_from = input(f"Вылет туда с (YYYY-MM-DD) [{args.depart_from}]: ").strip()
    if raw_from:
        args.depart_from = raw_from

    raw_to = input(f"Вылет туда по (YYYY-MM-DD) [{args.depart_to}]: ").strip()
    if raw_to:
        args.depart_to = raw_to

    raw_stay_min = input(f"Мин. дней пребывания [{args.stay_min}]: ").strip()
    if raw_stay_min:
        args.stay_min = int(raw_stay_min)

    raw_stay_max = input(f"Макс. дней пребывания [{args.stay_max}]: ").strip()
    if raw_stay_max:
        args.stay_max = int(raw_stay_max)

    raw_price = input(f"Макс. бюджет туда-обратно, ₽ [{args.max_price}]: ").strip()
    if raw_price:
        args.max_price = int(raw_price)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Поиск авиабилетов через Aviasales / Travelpayouts API")
    parser.add_argument("--origins", nargs="+", default=list(ORIGINS),
                        help="Коды IATA городов вылета (например: GOJ MOW LED)")
    parser.add_argument("--destinations", "--destination", nargs="+", dest="destinations",
                        default=list(DESTINATIONS),
                        help="Коды IATA пунктов назначения, можно несколько (например: SGN DAD CXR)")
    parser.add_argument("--depart-from", default=DEPART_FROM.isoformat(),
                        help="Начало окна вылета туда в формате YYYY-MM-DD")
    parser.add_argument("--depart-to", default=DEPART_TO.isoformat(),
                        help="Конец окна вылета туда в формате YYYY-MM-DD")
    parser.add_argument("--stay-min", type=int, default=STAY_MIN_DAYS,
                        help="Минимальная длительность поездки (дней)")
    parser.add_argument("--stay-max", type=int, default=STAY_MAX_DAYS,
                        help="Максимальная длительность поездки (дней)")
    parser.add_argument("--max-price", type=int, default=MAX_PRICE,
                        help="Максимальная цена билета туда-обратно (руб)")
    parser.add_argument("--max-transfers", type=int, default=MAX_TRANSFERS,
                        help="Максимум пересадок в одну сторону")
    parser.add_argument("--max-duration", type=float, default=MAX_DURATION_HOURS,
                        help="Максимум часов в пути в одну сторону")
    parser.add_argument("--top-n", type=int, default=TOP_N,
                        help="Сколько лучших вариантов вывести")
    parser.add_argument("--token", default=TOKEN,
                        help="Токен Travelpayouts API (по умолчанию из TP_TOKEN)")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Интерактивный выбор маршрута и дат перед запуском")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.interactive:
        _prompt_interactive(args)

    if not args.token:
        sys.exit("Задайте токен: export TP_TOKEN='ваш_токен' или --token 'ваш_токен' (travelpayouts.com)")

    rows = collect(
        token=args.token,
        origins=args.origins,
        destinations=args.destinations,
        depart_from=args.depart_from,
        depart_to=args.depart_to,
        stay_min_days=args.stay_min,
        stay_max_days=args.stay_max,
        max_price=args.max_price,
        max_transfers=args.max_transfers,
        max_duration_hours=args.max_duration,
    )
    print_table(rows, top_n=args.top_n)
    save_csv(rows)
    notify_telegram(rows, destination=",".join(args.destinations))
    if rows:
        print(f"\nВсе результаты сохранены в {CSV_FILE}")


if __name__ == "__main__":
    main()
