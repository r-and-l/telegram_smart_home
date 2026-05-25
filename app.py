# pyrefly: ignore [missing-import]
import appdaemon.plugins.hass.hassapi as hass

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