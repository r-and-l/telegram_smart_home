DEVICES = [
    {
        "name": "🚪 Коридор",
        "entity": "switch.svet_v_koridore_vykliuchatel",
        "type": "lights",
        "room": "hallway",
        "timer_minutes": 15
    },
    {
        "name": "🚽 Туалет",
        "entity": "switch.svet_v_tualete_vykliuchatel",
        "type": "lights",
        "room": "toilet",
        "timer_minutes": 10
    },
    {
        "name": "🛁 Ванная",
        "entity": "switch.svet_v_vannoi_vykliuchatel",
        "type": "lights",
        "room": "bathroom",
        "timer_minutes": 10
    },
    {
        "name": "🍳 Кухня общ.",
        "entity": "switch.svet_osnovnoi_vykliuchatel_2",
        "type": "lights",
        "room": "kitchen",
        "timer_minutes": 120
    },
    {
        "name": "🍳 Кухня раб.",
        "entity": "switch.rabochii_svet_vykliuchatel",
        "type": "lights",
        "room": "kitchen",
        "timer_minutes": 120
    },
    {
        "name": "🛋️ Гостинная",
        "entity": "switch.svet_osnovnoi_vykliuchatel",
        "type": "lights",
        "room": "living",
        "timer_minutes": 60
    },
    {
        "name": "💤 Спальня",
        "entity": "switch.svet_v_spalne_vykliuchatel",
        "type": "lights",
        "room": "bedroom",
        "timer_minutes": 30
    },
    {
        "name": "💼 Оффис",
        "entity": "switch.svet_v_igrovoi_vykliuchatel_2",
        "type": "lights",
        "room": "office",
        "timer_minutes": 180
    },
    {
        "name": "🚿 Вытяжка ванна",
        "entity": "light.lumi_lumi_relay_c2acn01_osveshchenie",
        "type": "climate",
        "room": "bathroom"
    },
    {
        "name": "🚽 Вытяжка туалет",
        "entity": "light.lumi_lumi_relay_c2acn01_osveshchenie_2",
        "type": "climate",
        "room": "toilet"
    },
    {
        "name": "❄️ Кондиционер",
        "entity": "climate.kondicioner",
        "type": "climate",
        "room": "bedroom"
    },
    {
        "name": "🛋️ Гостинная",
        "entity": "",
        "type": "blinds",
        "room": "living"
    },
    {
        "name": "💤 Спальня",
        "entity": "cover.shtory_v_spalne_ograzhdaiushchee_ustroistvo",
        "type": "blinds",
        "room": "bedroom"
    },
    {
        "name": "💼 Оффис",
        "entity": "",
        "type": "blinds",
        "room": "office"
    },
    {
        "name": "🌤️ Погода",
        "entity": "weather.forecast_home_assistant",
        "type": "weather",
        "room": "outside"
    },
    {
        "name": "🌖 Луна",
        "entity": "sensor.moon_phase",
        "type": "weather",
        "room": "outside"
    },
    {
        "name": "🌅 Восход",
        "entity": "sensor.sun_next_rising",
        "type": "weather",
        "room": "outside"
    },
    {
        "name": "🌇 Закат",
        "entity": "sensor.sun_next_setting",
        "type": "weather",
        "room": "outside"
    }
]

CATEGORIES = {
    "lights": {
        "title": "🏠 *Освещение*\n\n",
        "button_label": "💡 Свет",
    },
    "climate": {
        "title": "🌬 *Климат*\n\n",
        "button_label": "🌡 Климат",
    },
    "blinds": {
        "title": "🪟 *Шторы*\n\n",
        "button_label": "🪟 Шторы",
    },
    "weather": {
        "title": "🌤 *Погода*\n\n",
        "button_label": "🌤 Погода",
    },
}

# Настройки для мониторинга света
LIGHT_MONITOR_CONFIG = {
    "group_notification_window": 5,  # Минуты, в течение которых группировать уведомления
    "notification_entity": "notify.102_info_dom_milyi_dom",  # Сущность для отправки уведомлений
}
