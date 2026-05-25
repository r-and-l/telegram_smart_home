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
        self.log_discovered_entities()

    def log_discovered_entities(self):
        """Сканирует Home Assistant и выводит в лог список доступных сущностей для удобного добавления в config.py"""
        try:
            all_states = self.get_state()
            if not isinstance(all_states, dict):
                return
            
            # Извлекаем уже настроенные сущности, чтобы не показывать их как "новые"
            configured_entities = set()
            from config import DEVICES
            for d in DEVICES:
                entity_data = d.get("entity")
                if not entity_data:
                    continue
                if isinstance(entity_data, str):
                    configured_entities.add(entity_data)
                elif isinstance(entity_data, list):
                    configured_entities.update(entity_data)
                elif isinstance(entity_data, dict):
                    configured_entities.update(entity_data.values())

            domains_to_discover = ["light", "switch", "climate", "cover", "sensor"]
            discovered = {domain: [] for domain in domains_to_discover}

            for entity_id, state_info in all_states.items():
                if entity_id in configured_entities:
                    continue
                
                parts = entity_id.split(".")
                if len(parts) != 2:
                    continue
                domain, object_id = parts
                
                if domain not in domains_to_discover:
                    continue
                
                # Дополнительно фильтруем сенсоры: нам интересны в основном температура, влажность, освещенность, батарейки и т.д.
                if domain == "sensor":
                    friendly_name = ""
                    device_class = ""
                    if isinstance(state_info, dict):
                        attrs = state_info.get("attributes", {})
                        friendly_name = attrs.get("friendly_name", "").lower()
                        device_class = attrs.get("device_class", "") or ""
                    
                    is_candidate = any(keyword in entity_id or keyword in friendly_name 
                                       for keyword in ["temp", "humid", "vlag", "vlazh", "co2", "press", "pressure", "illumin", "lux", "bat"])
                    is_candidate = is_candidate or device_class in ["temperature", "humidity", "co2", "pressure", "illuminance", "battery"]
                    if not is_candidate:
                        continue

                friendly_name = ""
                if isinstance(state_info, dict):
                    friendly_name = state_info.get("attributes", {}).get("friendly_name", "")
                
                discovered[domain].append((entity_id, friendly_name))

            # Логируем результаты в красивом виде
            self.log("=== ОБНАРУЖЕНЫ НОВЫЕ СУЩНОСТИ В HOME ASSISTANT ===")
            for domain, items in discovered.items():
                if not items:
                    continue
                self.log(f"Домен {domain.upper()}:")
                for entity_id, friendly_name in sorted(items):
                    name_part = f" ({friendly_name})" if friendly_name else ""
                    self.log(f"  - {entity_id}{name_part}")
            self.log("==================================================")
        except Exception as e:
            self.log(f"Ошибка при поиске новых сущностей: {e}")