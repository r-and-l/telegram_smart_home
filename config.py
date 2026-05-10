DEVICES = [
    {
        "name": "🚪 Коридор",
        "entity": "switch.svet_v_koridore_vykliuchatel",
        "type": "lights",
        "room": "hallway"
    },
    {
        "name": "🚽 Туалет",
        "entity": "switch.svet_v_tualete_vykliuchatel",
        "type": "lights",
        "room": "toilet"
    },
    {
        "name": "🛁 Ванная",
        "entity": "switch.svet_v_vannoi_vykliuchatel",
        "type": "lights",
        "room": "bathroom"
    },
    {
        "name": "🍳 Кухня общ.",
        "entity": "switch.svet_osnovnoi_vykliuchatel_2",
        "type": "lights",
        "room": "kitchen"
    },
    {
        "name": "🍳 Кухня раб.",
        "entity": "switch.rabochii_svet_vykliuchatel",
        "type": "lights",
        "room": "kitchen"
    },
    {
        "name": "🛋️ Гостинная",
        "entity": "switch.svet_osnovnoi_vykliuchatel",
        "type": "lights",
        "room": "living"
    },
    {
        "name": "💤 Спальня",
        "entity": "switch.svet_v_spalne_vykliuchatel",
        "type": "lights",
        "room": "bedroom"
    },
    {
        "name": "💼 Оффис",
        "entity": "switch.svet_v_igrovoi_vykliuchatel_2",
        "type": "lights",
        "room": "office"
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
