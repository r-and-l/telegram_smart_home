from datetime import datetime

def build_rooms_text(app, rooms):
    text = "🏠 *Освещение*\n\n"
    for name, entity in rooms:
        state = app.get_state(entity)
        icon = "🟢" if state == "on" else "⚫"
        text += f"{icon} {name}"
        if state == "on":
            last_changed = app.get_state(
                entity,
                attribute="last_changed"
            )
            if last_changed:
                changed_time = datetime.fromisoformat(
                    last_changed.replace("Z", "+00:00")
                )
                minutes = int(
                    (
                        datetime.now(changed_time.tzinfo)
                        - changed_time
                    ).total_seconds() / 60
                )
                text += f"  💡 {minutes} мин"
        text += "\n"
    return text