class Router:
    def __init__(self, app, menu_manager, light_monitor, automations, telegram_api):
        self.app = app
        self.menu_manager = menu_manager
        self.light_monitor = light_monitor
        self.automations = automations
        self.telegram = telegram_api

        self.app.listen_event(self.telegram_command, "telegram_command")
        self.app.listen_event(self.inline_callback, "telegram_callback")

    def telegram_command(self, event_name, data, kwargs):
        command = data.get("command")
        chat_id = data.get("chat_id")
        self.app.log(f"📥 RECEIVED COMMAND: {command} (chat: {chat_id})")
        self.telegram.update_chat_id(chat_id)

        if command == "/start":
            self.telegram.reset_message_id()
            self.menu_manager.show_main_menu()

    def inline_callback(self, event_name, data, kwargs):
        command = data.get("command", "")
        chat_id = data.get("chat_id")
        self.app.log(f"🔘 RECEIVED CALLBACK: {command} (chat: {chat_id})")
        self.telegram.update_chat_id(chat_id)
        
        if command.startswith("/menu:ac:"):
            entity_id = command.replace("/menu:ac:", "")
            self.menu_manager.show_ac_menu(entity_id)

        elif command.startswith("/menu:"):
            category = command.replace("/menu:", "")
            self.menu_manager.show_menu(category)
            
        elif command.startswith("/ac:mode:"):
            # format: /ac:mode:climate.entity_id:cool
            parts = command.split(":")
            if len(parts) == 4:
                entity = parts[2]
                mode = parts[3]
                
                # Специальная обработка бризера (fresh_air). В miot это может быть либо preset_mode, либо отдельный switch.
                # Для начала попробуем передать как preset_mode, если это не поможет — пользователь сможет адаптировать логику.
                if mode == "fresh_air":
                    self.app.call_service("climate/set_preset_mode", entity_id=entity, preset_mode="fresh_air")
                else:
                    self.app.call_service("climate/set_hvac_mode", entity_id=entity, hvac_mode=mode)
                    
            if self.menu_manager.current_menu:
                self.menu_manager.show_ac_menu(entity)
                
        elif command.startswith("/ac:temp:"):
            # format: /ac:temp:climate.entity_id:up
            parts = command.split(":")
            if len(parts) == 4:
                entity = parts[2]
                direction = parts[3]
                current_temp = self.app.get_state(entity, attribute="temperature")
                if current_temp is not None:
                    try:
                        new_temp = float(current_temp) + (1.0 if direction == "up" else -1.0)
                        self.app.call_service("climate/set_temperature", entity_id=entity, temperature=new_temp)
                    except ValueError:
                        pass
            if self.menu_manager.current_menu:
                self.menu_manager.show_ac_menu(entity)

        elif command.startswith("/ac:fan:"):
            # format: /ac:fan:climate.entity_id:low
            parts = command.split(":")
            if len(parts) == 4:
                entity = parts[2]
                fan_mode = parts[3]
                self.app.call_service("climate/set_fan_mode", entity_id=entity, fan_mode=fan_mode)
            if self.menu_manager.current_menu:
                self.menu_manager.show_ac_menu(entity)
        
        elif command.startswith("/toggle:"):
            entity = command.replace("/toggle:", "")
            self.app.call_service("homeassistant/toggle", entity_id=entity)
            if self.menu_manager.current_menu:
                # Menu auto_update will pick up the change, 
                # but to be responsive, we trigger render manually
                self.menu_manager.show_menu(self.menu_manager.current_menu)
        
        elif command == "/back":
            self.menu_manager.show_main_menu()
        
        elif command.startswith("/turn_off:"):
            entity = command.replace("/turn_off:", "")
            self.light_monitor.turn_off(entity)
        
        elif command.startswith("/turn_off_all:"):
            entities = command.replace("/turn_off_all:", "").split(",")
            self.light_monitor.turn_off_all(entities)
        
        elif command == "/night_mode":
            self.automations.activate_night_mode()
