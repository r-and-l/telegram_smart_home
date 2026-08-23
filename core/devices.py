"""
Индексы и хелперы для доступа к DEVICES.

DEVICES — плоский список словарей, и раньше по нему выполнялся линейный
поиск на каждый рендер меню и каждое событие состояния. Здесь индексы
строятся один раз при импорте модуля.
"""

from config import DEVICES

# entity (str) -> device
BY_ENTITY = {}
# type -> [device, ...] с сохранением порядка из config
BY_TYPE = {}


def entity_ids(device):
    """Все сущности устройства: строка, список или dict вида {'temperature': ...}."""
    entity_data = device.get("entity")
    if not entity_data:
        return []
    if isinstance(entity_data, str):
        return [entity_data]
    if isinstance(entity_data, list):
        return [e for e in entity_data if isinstance(e, str)]
    if isinstance(entity_data, dict):
        return [e for e in entity_data.values() if isinstance(e, str)]
    return []


def _build_index():
    BY_ENTITY.clear()
    BY_TYPE.clear()
    for device in DEVICES:
        BY_TYPE.setdefault(device.get("type"), []).append(device)
        for entity in entity_ids(device):
            BY_ENTITY.setdefault(entity, device)


_build_index()


def by_type(device_type):
    """Устройства указанного типа (lights / climate / blinds / weather)."""
    return BY_TYPE.get(device_type, [])


def by_entity(entity):
    """Устройство по любой из его сущностей, либо None."""
    return BY_ENTITY.get(entity)


def name_of(entity, default=None):
    device = BY_ENTITY.get(entity)
    return device["name"] if device else (default if default is not None else entity)


def controllable(device_type):
    """[(name, entity)] — только устройства с одной управляемой сущностью-строкой."""
    return [
        (d["name"], d["entity"])
        for d in by_type(device_type)
        if isinstance(d.get("entity"), str) and d["entity"]
    ]


def lights():
    """Светильники с заданной сущностью — источник для мониторинга таймеров."""
    return [d for d in by_type("lights") if isinstance(d.get("entity"), str) and d["entity"]]


def all_monitored_entities():
    """Все сущности из конфига — для регистрации слушателей состояния."""
    return list(BY_ENTITY.keys())
