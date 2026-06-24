# mruby/c Workbench — PIC32MX170F256B

A lightweight desktop environment for writing, simulating, and flashing **mruby/c** programs to the **PIC32MX170F256B** microcontroller — all from one window.

---

## What This Is

This is **not** a full IDE. It is a purpose-built, single-window tool that connects three things you already need:

| Step | Tool |
|---|---|
| Write Ruby code | Built-in editor with syntax highlighting |
| Compile to bytecode | `mrbc` (mruby compiler) |
| Test on your desktop | `simulator.exe` — a virtual PIC32 environment |
| Flash to real hardware | `mrbwrite.exe` — writes `.mrb` over UART to your board |

---

## Features

- **Code editor** — Dark-themed, Ruby syntax highlighting, line numbers, error markers
- **One-click compile** — Runs `mrbc` and shows errors inline in the editor
- **Built-in simulator** — Output streams directly into the editor's console, no separate window
- **GPIO simulation** — `GPIO.new`, `gpio.write`, `gpio.read`, `sleep` and `loop` all work
- **Flash writer** — Integrated `mrbwrite` with COM port selection and baud rate config
- **Settings dialog** — Configure all tool paths without touching any file

---

## Requirements

### To run the editor
- **Python 3.8+**
- **PyQt6** or **tkinter** (tkinter is bundled with Python on Windows)
- `pyserial` *(optional — improves COM port detection)*

```bash
pip install pyserial
```

### To compile Ruby code
- **mrbc** — the mruby compiler

  On Windows with MSYS2 UCRT64:
  ```bash
  pacman -S mingw-w64-ucrt-x86_64-mruby
  ```

### To flash to the real board
- A PIC32MX170F256B board running the **mruby/c firmware** with UART programming support
- `mrbwrite.exe` is already included as a pre-built binary

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/yourname/mrubyc-workbench.git
cd mrubyc-workbench

# 2. Launch the editor
python main.py
```

On first launch, go to **Settings → Tool Paths** to point the editor at your `mrbc.exe` on disk.

---

## Usage

### Writing Code

Write standard mruby/c-compatible Ruby in the editor. The supported subset follows the [mruby/c language spec](https://github.com/mrubyc/mrubyc).

**Example — blink an LED:**
```ruby
gpio = GPIO.new(5, GPIO::OUT)

loop do
  gpio.write(1)
  sleep(1)
  gpio.write(0)
  sleep(1)
end
```

### Compiling

Click **Compile** (or press `Ctrl+B`). If there are errors, the offending line is highlighted in red and the message appears in the console.

### Running in the Simulator

Click **Run in Simulator**. The virtual PIC32 boots, loads your bytecode into simulated 256 KB Flash, and runs the mruby/c VM. All `puts` output appears live in the console. Press **Stop** to kill it at any time.

### Flashing to the Board

1. Select your COM port from the dropdown (auto-detected).
2. Click **Write to Board**.
3. The editor runs `mrbwrite` and streams its output to the console.

> **Note:** The board must be in programming mode. Power-cycle it (or press SW1) while `mrbwrite` is running.

---

## Simulated Peripherals

The simulator implements a real software model of the PIC32MX170F256B peripheral registers.

| Class / Method | Description |
|---|---|
| `GPIO.new(pin, mode)` | Configure a GPIO pin |
| `GPIO::OUT`, `GPIO::IN` | Pin direction constants |
| `GPIO::PULL_UP`, `GPIO::PULL_DOWN`, `GPIO::HIGH_Z` | Input mode constants |
| `gpio.write(value)` | Drive pin HIGH (1) or LOW (0) |
| `gpio.read` | Read pin state |
| `gpio.high?` / `gpio.low?` | Predicate methods |
| `leds_write(mask)` | Control up to 4 onboard LEDs by bitmask |
| `sw` | Read the onboard switch state |
| `sleep(seconds)` | Real-time delay |

---

## Project Structure

```
.
├── main.py                          # The desktop editor (Python/Tkinter)
├── simulator.exe                    # Pre-built Windows simulator binary
├── mrbwrite.exe                     # Pre-built Windows flash writer binary
├── simulator_main.cpp               # Simulator entry point and VM setup
├── model_dependent.cpp / .h         # Simulated PIC32 peripheral register layer
├── pic32mx.h / xc.h                 # Hardware abstraction headers
├── Makefile                         # Build system for simulator.exe
├── sys/                             # Compiler compatibility shims
├── mrbwrite/                        # mrbwrite source code (submodule)
│   ├── mrbwrite.cpp
│   ├── mrbwrite.h
│   └── mrbwrite.pro                 # Qt project file
└── pic32mx170_mrubyc-master/        # mruby/c VM source code
    └── src/                         # VM core (vm.c, alloc.c, class.c, ...)
```

---

## Building from Source

If you want to recompile `simulator.exe` yourself, you need the **MSYS2 UCRT64** toolchain:

```bash
# Install MSYS2 from https://www.msys2.org, then:
pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-mruby

# In the project root (using UCRT64 shell):
make
```

To recompile `mrbwrite.exe`, Qt6 with SerialPort support is required:
```bash
pacman -S mingw-w64-ucrt-x86_64-qt6-base mingw-w64-ucrt-x86_64-qt6-serialport

cd mrbwrite
qmake mrbwrite.pro
make release
```

---

## Credits

- **[mruby/c](https://github.com/mrubyc/mrubyc)** — Lightweight Ruby VM for embedded systems by Kyushu Institute of Technology
- **[mrbwrite](https://github.com/mrubyc/mrbwrite)** — UART flash writer for mruby/c boards

---

## License

The editor and simulator code in this repository is released under the **BSD 3-Clause License**.

The bundled `mrbwrite` and `mruby/c VM` source code retain their original licenses — see `mrbwrite/LICENSE` and `pic32mx170_mrubyc-master/pic32mx170_mrubyc-master/` respectively.
