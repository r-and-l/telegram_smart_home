# pyrefly: ignore [missing-import]
import appdaemon.plugins.hass.hassapi as hass
import sys
import importlib

# Динамическая перезагрузка всех подмодулей проекта при сохранении app.py
for mod in list(sys.modules.keys()):
    if any(mod.startswith(p) for p in ("core", "services", "ui", "config")):
        try:
            importlib.reload(sys.modules[mod])
        except Exception:
            pass

from core.telegram_api import TelegramAPI
from core.router import Router
from services.menu_manager import MenuManager
from services.light_monitor import LightMonitor
from services.automations import Automations

class TelegramSmartHome(hass.Hass):

    def initialize(self):
        self.telegram_api = TelegramAPI(self)
        self.menu_manager = MenuManager(self, self.telegram_api)
        self.light_monitor = LightMonitor(self, self.telegram_api)
        self.automations = Automations(self, self.telegram_api, self.menu_manager)
        
        self.router = Router(
            app=self,
            menu_manager=self.menu_manager,
            light_monitor=self.light_monitor,
            automations=self.automations,
            telegram_api=self.telegram_api
        )

        self.run_every(
            self.menu_manager.auto_update,
            "now",
            60
        )

        self.log("SMART HOME BOT STARTED")
        # reload trigger