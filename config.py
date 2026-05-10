DEVICES = {
    "lights": {
        "title": "🏠 *Освещение*\n\n",
        "button_label": "💡 Свет",
        "items": [
            ("🚪 Коридор", "switch.svet_v_koridore_vykliuchatel", "hallway"),
            ("🚽 Туалет", "switch.svet_v_tualete_vykliuchatel", "toilet"),
            ("🛁 Ванная", "switch.svet_v_vannoi_vykliuchatel", "bathroom"),
            ("🍳 Кухня общ.", "switch.svet_osnovnoi_vykliuchatel_2", "kitchen"),
            ("🍳 Кухня раб.", "switch.rabochii_svet_vykliuchatel", "kitchen"),
            ("🛋️ Гостинная", "switch.svet_osnovnoi_vykliuchatel", "living"),
            ("💤 Спальня", "switch.svet_v_spalne_vykliuchatel", "bedroom"),
            ("💼 Оффис", "switch.svet_v_igrovoi_vykliuchatel_2", "office"),
        ],
    },
    "climate": {
        "title": "🌬 *Климат*\n\n",
        "button_label": "🌡 Климат",
        "items": [
            ("🚿 Вытяжка ванна", "light.lumi_lumi_relay_c2acn01_osveshchenie", "bathroom"),
            ("🚽 Вытяжка туалет", "light.lumi_lumi_relay_c2acn01_osveshchenie_2", "toilet"),
            ("❄️ Кондиционер", "climate.kondicioner", "bedroom"),
        ],
    },
    "blinds": {
        "title": "🪟 *Шторы*\n\n",
        "button_label": "🪟 Шторы",
        "items": [
            ("🛋️ Гостинная", "", "living"),
            ("💤 Спальня", "cover.shtory_v_spalne_ograzhdaiushchee_ustroistvo", "bedroom"),
            ("💼 Оффис", "", "office"),
        ],
    },
}
