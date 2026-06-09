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
        self.app.log(f"📥 RECEIVED TELEGRAM COMMAND: {data}")
        command = data.get("command")
        chat_id = data.get("chat_id")
        self.telegram.update_chat_id(chat_id)

        if command == "/start":
            self.telegram.reset_message_id()
            self.menu_manager.show_main_menu()

    def inline_callback(self, event_name, data, kwargs):
        self.app.log(f"🔘 RECEIVED TELEGRAM CALLBACK: {data}")
        command = data.get("command", "")
        chat_id = data.get("chat_id")
        self.telegram.update_chat_id(chat_id)
        
        if command.startswith("/menu:"):
            category = command.replace("/menu:", "")
            self.menu_manager.show_menu(category)
        
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
