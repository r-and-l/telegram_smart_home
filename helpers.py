def build_keyboard(items, per_row=3):

    keyboard = []
    row = []

    for i, item in enumerate(items, start=1):

        row.append(item)

        if i % per_row == 0:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    return keyboard