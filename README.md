# Project Stella Montis

Project Stella Montis (PSM) changes the monitor gamma while Arc Raiders is the foreground window. Dark areas stay readable. Bright areas are not left blown out. The adjustment is automatic, so gamma does not have to be set by hand in the NVIDIA panel or anywhere else.

Menus and inventory are recognised from the picture; gamma is left alone there. The program reads the desktop image and writes the monitor gamma ramp. It does not read the game process, inject anything, or send input.

Works in borderless or windowed mode; exclusive full screen hides both the overlay and the gamma ramp. The interface follows the Windows language: Russian when Windows is Russian, English otherwise. One run as administrator lifts the Windows cap on gamma ramps (`GdiIcmGammaRange`); without it the ceiling stays around 1.4–1.5.

## Settings

Saved to `PSM.ini` on every change. Next to `psm.py` when you run from source; in `%LOCALAPPDATA%\\Project Stella Montis` when you run the installed build.

| Tab | Control | Meaning |
|-----|---------|---------|
| Gamma | Gamma max / min | Ceiling for dark scenes, floor for bright ones |
| Gamma | Trigger threshold | Smallest change of target that moves the gamma |
| Gamma | Mode | Auto, or a fixed manual gamma |
| Circle | Diameter | Sampling circle, % of the game window height |
| Circle | Show area on screen | Green overlay of the circle and the curve rings |
| Circle | Influence curve | How much the center counts versus the rim |
| Polling | Brightness poll interval | How often the circle is sampled |
| Polling | Game status poll interval | How often the ESC button is checked |
| Polling | Compute device | GPU shader or CPU numpy for the circle average |

## Project structure

| Path | Role |
|------|------|
| `psm.py` | Entry point |
| `src/core/` | Paths, settings, interface strings |
| `src/kernel/` | Windows boundary: window lookup, gamma ramps, DXGI capture |
| `src/modules/` | Menu detector, influence curve |
| `src/daemon/` | The background loop |
| `src/ui/` | The window |
| `assets/` | ESC outline template, window icon |

How the loop is wired: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Build

Windows, Python 3.10. Runtime dependencies are `requirements.txt`. Nuitka needs a C compiler; if none is installed it can download MinGW.

```powershell
pip install -r requirements.txt nuitka
$env:PYTHONPATH = "src"
python -m nuitka --standalone --windows-console-mode=disable `
  --windows-icon-from-ico=assets/icon.ico --enable-plugin=tk-inter `
  --include-package=dxcam --include-package=comtypes `
  --include-package-data=dxcam --include-data-dir=assets=assets `
  --output-dir=build --output-filename="Project Stella Montis.exe" `
  --company-name=Factiosi --product-name="Project Stella Montis" `
  --file-version=1.0.1.0 --product-version=1.0.1.0 `
  --file-description="Project Stella Montis" psm.py
```

`PYTHONPATH` has to include `src`, or Nuitka does not see the packages. `--file-version` and `--product-version` are the number in `pyproject.toml` plus a fourth `.0`. The executable is `build/psm.dist/Project Stella Montis.exe`. `PSM.ini` and `psm_baseline.dat` are not in that folder; the program writes them beside itself when it runs.

The installer is Inno Setup 6: compile `installer/setup.iss` after the folder above exists. The setup file is `installer/output/Project Stella Montis 1.0.1.exe`. The script does not pack `PSM.ini` or the saved ramp.

---

# Project Stella Montis

Project Stella Montis (PSM) меняет гамму монитора, пока Arc Raiders на переднем плане. Тёмные участки остаются читаемыми. Светлые не остаются выжженными. Регулировка автоматическая: гамму не нужно выставлять руками в панели NVIDIA или где-либо ещё.

Меню и инвентарь определяются по картинке; гамма там не меняется. Программа читает изображение рабочего стола и пишет гамма-рампу монитора. Память игры не читается, ничего не внедряется, ввод не посылается.

Работает в режиме без рамки или в окне; эксклюзивный полный экран прячет и оверлей, и рампу. Язык интерфейса совпадает с языком Windows: русский, если Windows на русском, иначе английский. Один запуск от администратора снимает потолок Windows на гамма-рампы (`GdiIcmGammaRange`); без него потолок около 1.4–1.5.

## Настройки

Пишутся в `PSM.ini` при каждом изменении. Рядом с `psm.py` при запуске из исходников; в `%LOCALAPPDATA%\\Project Stella Montis` у установленной сборки.

| Вкладка | Элемент | Смысл |
|---------|---------|-------|
| Гамма | Гамма макс. / мин. | Потолок на тёмных сценах, пол на ярких |
| Гамма | Порог срабатывания | Наименьшее смещение цели, после которого гамма едет |
| Гамма | Режим | Авто или фиксированная ручная гамма |
| Круг | Диаметр | Круг замера, % высоты окна игры |
| Круг | Показать область на экране | Зелёный оверлей круга и колец кривой |
| Круг | Кривая влияния | Сколько весит центр относительно края |
| Опрос | Частота опроса яркости | Как часто снимается круг |
| Опрос | Частота опроса статуса игры | Как часто проверяется кнопка ESC |
| Опрос | Мощности вычисления | Шейдер на видеокарте или numpy на процессоре |

## Структура проекта

| Путь | Роль |
|------|------|
| `psm.py` | Вход |
| `src/core/` | Пути, настройки, строки интерфейса |
| `src/kernel/` | Граница с Windows: окно, рампы гаммы, захват DXGI |
| `src/modules/` | Детектор меню, кривая влияния |
| `src/daemon/` | Фоновый цикл |
| `src/ui/` | Окно |
| `assets/` | Шаблон контура ESC, значок окна |

Как устроен цикл: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Сборка

Windows, Python 3.10. Зависимости для запуска — `requirements.txt`. Nuitka нужен компилятор C; если его нет, Nuitka может скачать MinGW.

```powershell
pip install -r requirements.txt nuitka
$env:PYTHONPATH = "src"
python -m nuitka --standalone --windows-console-mode=disable `
  --windows-icon-from-ico=assets/icon.ico --enable-plugin=tk-inter `
  --include-package=dxcam --include-package=comtypes `
  --include-package-data=dxcam --include-data-dir=assets=assets `
  --output-dir=build --output-filename="Project Stella Montis.exe" `
  --company-name=Factiosi --product-name="Project Stella Montis" `
  --file-version=1.0.1.0 --product-version=1.0.1.0 `
  --file-description="Project Stella Montis" psm.py
```

`PYTHONPATH` должен включать `src`, иначе Nuitka не видит пакеты. `--file-version` и `--product-version` — номер из `pyproject.toml` и четвёртый компонент `.0`. Файл — `build/psm.dist/Project Stella Montis.exe`. `PSM.ini` и `psm_baseline.dat` в эту папку не входят: программа пишет их рядом с собой при запуске.

Установщик — Inno Setup 6: компилировать `installer/setup.iss`, когда папка выше уже есть. Файл установки — `installer/output/Project Stella Montis 1.0.1.exe`. Скрипт не кладёт в пакет `PSM.ini` и сохранённую рампу.
