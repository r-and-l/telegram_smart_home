import copy
import json
import os
import tempfile

_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state.json")


class Store:
    """
    Единое персистентное хранилище состояния бота (state.json).

    Держит весь стейт в памяти и атомарно сбрасывает его на диск,
    чтобы перезагрузка модулей или рестарт AppDaemon не терял
    message_id уведомлений и пользовательские таймеры.
    """

    def __init__(self, app, path=None):
        self.app = app
        self.path = path or _STATE_FILE
        self.data = self._load()

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.app.log(f"LOADED PERSISTED STATE: {data}")
                    return data
        except Exception as e:
            self.app.log(f"Error loading persisted state: {e}")
        return {}

    def get(self, key, default=None):
        value = self.data.get(key)
        if value is None:
            return default
        # Копия, чтобы мутации у вызывающего не превращали сравнение в no-op
        return copy.deepcopy(value) if isinstance(value, (dict, list)) else value

    def set(self, key, value):
        if key in self.data and self.data[key] == value:
            return
        # Храним собственный снимок: вызывающий код продолжает мутировать свой объект
        self.data[key] = copy.deepcopy(value)
        self.save()

    def update(self, **values):
        if all(k in self.data and self.data[k] == v for k, v in values.items()):
            return
        self.data.update(copy.deepcopy(values))
        self.save()

    def save(self):
        """Атомарная запись: временный файл + os.replace, чтобы не оставить обрезанный JSON."""
        try:
            directory = os.path.dirname(self.path) or "."
            fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False)
                os.replace(tmp_path, self.path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
        except Exception as e:
            self.app.log(f"Error saving persisted state: {e}")
