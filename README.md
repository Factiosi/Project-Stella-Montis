# Project Stella Montis

Project Stella Montis (PSM) changes the monitor gamma while Arc Raiders is the foreground window. Dark areas stay readable. Bright areas are not left blown out. The adjustment is automatic, so gamma does not have to be set by hand in the NVIDIA panel or anywhere else.

Menus and inventory are recognised from the picture; gamma is left alone there. The program reads the desktop image and writes the monitor gamma ramp. It does not read the game process, inject anything, or send input.

Works in borderless or windowed mode; exclusive full screen hides both the overlay and the gamma ramp. The interface follows the Windows language: Russian when Windows is Russian, English otherwise. One run as administrator lifts the Windows cap on gamma ramps (`GdiIcmGammaRange`); without it the ceiling stays around 1.4–1.5.

## Settings

Saved to `PSM.ini` next to the program on every change.

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

---

# Project Stella Montis

Project Stella Montis (PSM) меняет гамму монитора, пока Arc Raiders на переднем плане. Тёмные участки остаются читаемыми. Светлые не остаются выжженными. Регулировка автоматическая: гамму не нужно выставлять руками в панели NVIDIA или где-либо ещё.

Меню и инвентарь определяются по картинке; гамма там не меняется. Программа читает изображение рабочего стола и пишет гамма-рампу монитора. Память игры не читается, ничего не внедряется, ввод не посылается.

Работает в режиме без рамки или в окне; эксклюзивный полный экран прячет и оверлей, и рампу. Язык интерфейса совпадает с языком Windows: русский, если Windows на русском, иначе английский. Один запуск от администратора снимает потолок Windows на гамма-рампы (`GdiIcmGammaRange`); без него потолок около 1.4–1.5.

## Настройки

Пишутся в `PSM.ini` рядом с программой при каждом изменении.

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
