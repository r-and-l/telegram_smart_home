DEVICES = {
    "lights": [
        ("🚪 Коридор", "switch.svet_v_koridore_vykliuchatel"),
        ("🚽 Туалет", "switch.svet_v_tualete_vykliuchatel"),
        ("🛁 Ванная", "switch.svet_v_vannoi_vykliuchatel"),
        ("🍳 Кухня", "switch.svet_osnovnoi_vykliuchatel_2"),
        ("🛋️ Гостинная", "switch.svet_osnovnoi_vykliuchatel"),
        ("💤 Спальня", "switch.svet_v_spalne_vykliuchatel"),
        ("💼 Оффис", "switch.svet_v_igrovoi_vykliuchatel_2"),
    ],
    "climate": [
        ("🚿 Вытяжка ванна", "light.lumi_lumi_relay_c2acn01_osveshchenie"),
        ("🚽 Вытяжка туалет", "light.lumi_lumi_relay_c2acn01_osveshchenie_2"),
        ("❄️ Кондиционер", "climate.kondicioner"),
    ],
    # Add more categories here
}

# Backward compatibility
ROOMS = DEVICES["lights"]
CLIMATE_DEVICES = DEVICES["climate"]