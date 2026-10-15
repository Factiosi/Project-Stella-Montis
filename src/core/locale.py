"""UI copy. `GetUserDefaultUILanguage` primary id 0x19 → ru, anything else → en."""

from __future__ import annotations

import ctypes

LANG_RUSSIAN = 0x19

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "header_tag": "GAMMA  //  ARC RAIDERS",
        "status_label": "STATUS",
        "state_no_game": "Game not running",
        "state_unfocused": "Game not focused",
        "state_paused": "Paused",
        "state_menu": "In menu",
        "state_raid": "In raid",
        "state_error": "Error",
        "tag_manual": "MANUAL",
        "note_hdr": "HDR is on: the gamma ramp may have no effect.",
        "note_rejected": "The driver rejected gamma {value}.",
        "note_full_range": "Full gamma range is not enabled. Run once as administrator to lift the Windows cap.",
        "error_no_template": "Template missing: {value}",
        "error_capture_open": "Capture failed to open: {value}",
        "error_capture": "Capture failed: {value}",
        "tab_gamma": "Gamma",
        "tab_circle": "Circle",
        "tab_poll": "Polling",
        "gamma_max": "Gamma max",
        "gamma_min": "Gamma min",
        "threshold": "Trigger threshold",
        "mode": "Mode",
        "mode_auto": "Auto",
        "mode_manual": "Manual gamma",
        "diameter": "Circle diameter, % of window height",
        "show_overlay": "Show area on screen",
        "curve": "Influence curve",
        "preset_classic": "Default",
        "preset_center": "Center only",
        "preset_flat": "Linear",
        "curve_hint": "Double-click adds a point (up to 4). Right-click removes one. Drag to move.",
        "axis_x": "AREA SHARE FROM CENTER, %",
        "axis_y": "INFLUENCE, %",
        "capture_ms": "Brightness poll interval (ms)",
        "menu_ms": "Game status poll interval (ms)",
        "compute": "Compute device (load)",
        "compute_gpu": "GPU",
        "compute_cpu": "CPU",
        "compute_hint": (
            "GPU: a compute shader reduces the circle to a 96×96 grid; the CPU receives 36 KB per sample.\n"
            "CPU: the circle's bounding square is copied whole and averaged in numpy."
        ),
        "pause": "Pause",
        "resume": "Resume",
    },
    "ru": {
        "header_tag": "GAMMA  //  ARC RAIDERS",
        "status_label": "СТАТУС",
        "state_no_game": "Игра не запущена",
        "state_unfocused": "Игра не в фокусе",
        "state_paused": "Пауза",
        "state_menu": "В меню",
        "state_raid": "В рейде",
        "state_error": "Ошибка",
        "tag_manual": "РУЧНАЯ",
        "note_hdr": "HDR включён: рампа гаммы может не действовать.",
        "note_rejected": "Драйвер отклонил гамму {value}.",
        "note_full_range": "Полный диапазон гаммы не включён. Один запуск от администратора снимает потолок Windows.",
        "error_no_template": "Нет шаблона: {value}",
        "error_capture_open": "Захват не открылся: {value}",
        "error_capture": "Сбой захвата: {value}",
        "tab_gamma": "Гамма",
        "tab_circle": "Круг",
        "tab_poll": "Опрос",
        "gamma_max": "Гамма макс.",
        "gamma_min": "Гамма мин.",
        "threshold": "Порог срабатывания",
        "mode": "Режим",
        "mode_auto": "Авто",
        "mode_manual": "Ручная гамма",
        "diameter": "Диаметр круга, % высоты окна",
        "show_overlay": "Показать область на экране",
        "curve": "Кривая влияния",
        "preset_classic": "По умолчанию",
        "preset_center": "Только центр",
        "preset_flat": "Линейно",
        "curve_hint": "Двойной щелчок — новая точка (до 4). Правая кнопка — убрать. Точки можно тянуть.",
        "axis_x": "ДОЛЯ ПЛОЩАДИ ОТ ЦЕНТРА, %",
        "axis_y": "ВЛИЯНИЕ, %",
        "capture_ms": "Частота опроса яркости (в мс)",
        "menu_ms": "Частота опроса статуса игры (в мс)",
        "compute": "Мощности вычисления (нагрузка)",
        "compute_gpu": "Видеокарта",
        "compute_cpu": "Процессор",
        "compute_hint": (
            "Видеокарта: круг сжимается в сетку 96×96 шейдером, процессору достаётся 36 КБ на замер.\n"
            "Процессор: квадрат круга копируется целиком и усредняется в numpy."
        ),
        "pause": "Пауза",
        "resume": "Продолжить",
    },
}


def system_language() -> str:
    """`ru` or `en` from the Windows UI language, not the keyboard layout."""
    try:
        lang_id = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
    except (AttributeError, OSError):
        return "en"
    return "ru" if (lang_id & 0x3FF) == LANG_RUSSIAN else "en"


_language = system_language()


def set_language(code: str) -> None:
    global _language
    _language = code if code in STRINGS else "en"


def language() -> str:
    return _language


def tr(key: str, **values: object) -> str:
    """Look up `key` in the active table, then English, then the key itself."""
    table = STRINGS[_language]
    text = table.get(key) or STRINGS["en"].get(key) or key
    return text.format(**values) if values else text
