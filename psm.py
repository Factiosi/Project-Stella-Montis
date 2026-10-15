"""Entry: DPI awareness, then the settings window."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from kernel.window import enable_dpi_awareness, set_app_user_model_id

    set_app_user_model_id()
    enable_dpi_awareness()
    from ui.app import run

    run()


if __name__ == "__main__":
    main()
