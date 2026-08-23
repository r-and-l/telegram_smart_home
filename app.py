# pyrefly: ignore [missing-import]
import appdaemon.plugins.hass.hassapi as hass
import sys
import importlib

# Динамическая перезагрузка всех подмодулей проекта при сохранении app.py.
# config идёт первым: core.devices строит индексы по DEVICES на импорте,
# поэтому обновлённый конфиг должен быть в силе до его перезагрузки.
_project_modules = [
    mod for mod in list(sys.modules.keys())
    if any(mod.startswith(p) for p in ("core", "services", "ui", "config"))
]
for mod in sorted(_project_modules, key=lambda m: (not m.startswith("config"), m)):
    try:
        importlib.reload(sys.modules[mod])
    except Exception:
        pass

from config import LIGHT_MONITOR_CONFIG
from core.store import Store
from core.telegram_api import TelegramAPI
from core.router import Router
from services.menu_manager import MenuManager
from services.light_monitor import LightMonitor
from services.automations import Automations


class TelegramSmartHome(hass.Hass):

    def initialize(self):
        # Общее персистентное хранилище: id сообщений, уведомления, таймеры
        self.store = Store(self)

        self.telegram_api = TelegramAPI(self, store=self.store)
        self.light_monitor = LightMonitor(self, self.telegram_api, store=self.store)
        self.menu_manager = MenuManager(self, self.telegram_api, light_monitor=self.light_monitor)
        self.automations = Automations(self, self.telegram_api, self.menu_manager)

        self.router = Router(
            app=self,
            menu_manager=self.menu_manager,
            light_monitor=self.light_monitor,
            automations=self.automations,
            telegram_api=self.telegram_api
        )

        self.run_every(self.menu_manager.auto_update, "now", 60)

        # Сверка уведомлений с реальным состоянием света: убирает «висящие»
        # сообщения, если событие выключения было пропущено или удаление не удалось
        self.run_every(
            self.light_monitor.reconcile,
            "now",
            LIGHT_MONITOR_CONFIG.get("reconcile_interval", 60)
        )

        self.log("SMART HOME BOT STARTED")
