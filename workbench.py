#!/usr/bin/env python3
"""
mruby/c Desktop Workbench
=========================

A minimal, standalone desktop editor for the PIC32MX170F256B mruby/c workflow:

    write code -> compile (mrbc) -> simulate (simulator.exe) -> flash (mrbwrite)

This is NOT a full IDE. It is a single-file Tkinter application
that wraps three pre-built external executables and gives them a shared
editor + console + toolbar. No project system, no multi-file workspace.

Requires only the Python standard library. If the optional `pyserial`
package is installed, COM port detection is slightly nicer; otherwise the
app falls back to asking `mrbwrite --showline` for the port list, or lets
you type a port name directly into the dropdown.
"""

import json
import os
import re
import subprocess
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --------------------------------------------------------------------------
# Optional dependency: pyserial. Never required.
# --------------------------------------------------------------------------
try:
    from serial.tools import list_ports as _serial_list_ports
except ImportError:
    _serial_list_ports = None


APP_TITLE = "mruby/c Workbench"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")


def detect_default_mrbwrite_path():
    is_win = os.name == "nt"
    exe = "mrbwrite.exe" if is_win else "mrbwrite"
    candidates = [
        os.path.join(SCRIPT_DIR, exe),
        os.path.join(SCRIPT_DIR, "mrbwrite", exe),
        os.path.join(SCRIPT_DIR, "mrbwrite", "release", exe),
        os.path.join(SCRIPT_DIR, "mrbwrite", "deploy", "mrbwrite", exe),
        # qmake out-of-source build directories (Linux/Mac)
        os.path.join(SCRIPT_DIR, "build", exe),
        os.path.join(SCRIPT_DIR, "mrbwrite", "build", exe),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(SCRIPT_DIR, exe)

DEFAULT_CONFIG = {
    "mrbc_path": "C:/msys64/ucrt64/bin/mrbc.exe",
    "simulator_path": "./simulator.exe",
    "mrbwrite_path": detect_default_mrbwrite_path(),
    "baud_rate": "19200",
    "last_file": "",
    "last_com_port": "",
    "window_geometry": "1180x760",
}

BAUD_RATES = ["9600", "19200", "38400", "57600", "115200"]

# --------------------------------------------------------------------------
# Color theme (dark, low-glare, VS-Code-ish but its own palette)
# --------------------------------------------------------------------------
COL_BG = "#1b1e23"          # app background
COL_PANEL = "#21252b"       # toolbar / status bar
COL_EDITOR_BG = "#12141a"
COL_EDITOR_FG = "#e3e6eb"
COL_GUTTER_BG = "#181b21"
COL_GUTTER_FG = "#5b6271"
COL_CONSOLE_BG = "#0e1014"
COL_ACCENT = "#5fb3ff"
COL_ACCENT_DIM = "#3a7ab8"
COL_BORDER = "#30343c"
COL_TEXT_MUTED = "#8a909c"
COL_SUCCESS = "#56d364"
COL_ERROR = "#ff6b6b"
COL_WARN = "#ffb454"
COL_INFO = "#5fb3ff"
COL_CRITICAL_BG = "#3a1414"

# Syntax colors
COL_KEYWORD = "#d68fd6"
COL_STRING = "#d8a657"
COL_COMMENT = "#6a9955"
COL_NUMBER = "#9fd99f"
COL_CONSTANT = "#4ec9b0"
COL_SYMBOL = "#5fb3ff"
COL_IVAR = "#9cdcfe"
COL_BUILTIN = "#dcdcaa"
COL_ERROR_LINE_BG = "#3a1f1f"

EDITOR_FONT = ("Consolas", 12)
EDITOR_FONT_FALLBACK = ("Courier New", 12)
UI_FONT = ("Segoe UI", 9)
UI_FONT_FALLBACK = ("Helvetica", 9)


def pick_font(primary, fallback):
    """Return primary font tuple if usable, else fallback. Tk silently
    substitutes unknown families on most platforms, but we probe anyway so
    behavior is predictable."""
    try:
        import tkinter.font as tkfont
        families = set(tkfont.families())
        if primary[0] in families:
            return primary
    except Exception:
        pass
    return fallback


# --------------------------------------------------------------------------
# Config persistence
# --------------------------------------------------------------------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    else:
        save_config(cfg)

    # Prefer a cloned mrbwrite repo binary if available.
    mrbwrite_path = cfg.get("mrbwrite_path", "").strip()
    if (not mrbwrite_path or not os.path.isfile(mrbwrite_path)):
        cfg["mrbwrite_path"] = detect_default_mrbwrite_path()
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Ruby syntax highlighting (single-pass tokenizer via alternation)
# --------------------------------------------------------------------------
RUBY_KEYWORDS = [
    "__ENCODING__", "__LINE__", "__FILE__", "BEGIN", "END", "alias", "and",
    "begin", "break", "case", "class", "def", "defined?", "do", "else",
    "elsif", "end", "ensure", "false", "for", "if", "in", "module", "next",
    "nil", "not", "or", "redo", "rescue", "retry", "return", "self",
    "super", "then", "true", "undef", "unless", "until", "when", "while",
    "yield",
]
RUBY_BUILTINS = [
    "puts", "print", "p", "require", "require_relative", "attr_accessor",
    "attr_reader", "attr_writer", "loop", "sleep", "raise", "new", "lambda",
    "proc", "include", "extend", "freeze", "send", "respond_to?",
]

_TOKEN_SPECS = [
    ("COMMENT", r"#[^\n]*"),
    ("STRING", r'"(?:[^"\\\n]|\\.)*"' + r"|" + r"'(?:[^'\\\n]|\\.)*'"),
    ("SYMBOL", r":[A-Za-z_][A-Za-z0-9_]*[?!=]?"),
    ("IVAR", r"@{1,2}[A-Za-z_][A-Za-z0-9_]*"),
    ("GVAR", r"\$[A-Za-z_][A-Za-z0-9_]*"),
    ("NUMBER", r"\b\d+(?:\.\d+)?\b"),
    ("KEYWORD", r"\b(?:" + "|".join(re.escape(k) for k in RUBY_KEYWORDS) + r")\b"),
    ("BUILTIN", r"\b(?:" + "|".join(re.escape(k) for k in RUBY_BUILTINS) + r")\b"),
    ("CONSTANT", r"\b[A-Z][A-Za-z0-9_]*\b"),
]
_TOKEN_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPECS),
    re.MULTILINE,
)

_TAG_COLORS = {
    "COMMENT": COL_COMMENT,
    "STRING": COL_STRING,
    "SYMBOL": COL_SYMBOL,
    "IVAR": COL_IVAR,
    "GVAR": COL_IVAR,
    "NUMBER": COL_NUMBER,
    "KEYWORD": COL_KEYWORD,
    "BUILTIN": COL_BUILTIN,
    "CONSTANT": COL_CONSTANT,
}

# mrbc error lines look like:  somefile.rb:12:5: syntax error, unexpected ...
_MRBC_ERROR_RE = re.compile(r"^(.*?):(\d+):(\d+):\s*(.*)$")
# Fallback: anything with "line N" in it
_GENERIC_LINE_RE = re.compile(r"\bline\s+(\d+)\b", re.IGNORECASE)

MEMORY_ERROR_PATTERNS = ["Out of memory", "MAX_REGS_SIZE overflow"]
MEMORY_ERROR_TOOLTIP = "This code exceeded the 40 KB SRAM limit of the PIC32 device."


# --------------------------------------------------------------------------
# CustomText: a Text widget that fires <<Change>> on any edit or scroll,
# so the gutter and highlighter can stay in sync. (Standard Tk recipe.)
# --------------------------------------------------------------------------
class CustomText(tk.Text):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig = self._w + "_orig"
        self.tk.call("rename", self._w, self._orig)
        self.tk.createcommand(self._w, self._proxy)

    def _proxy(self, *args):
        try:
            result = self.tk.call((self._orig,) + args)
        except tk.TclError:
            return None
        changed = False
        if args and args[0] in ("insert", "delete", "replace"):
            changed = True
        elif len(args) >= 2 and args[0] in ("xview", "yview") and args[1] in ("moveto", "scroll"):
            changed = True
        elif len(args) >= 3 and args[0] == "mark" and args[1] == "set" and args[2] == "insert":
            changed = True
        if changed:
            self.event_generate("<<Change>>", when="tail")
        return result


# --------------------------------------------------------------------------
# Line-number gutter, synced to a CustomText via <<Change>>/<Configure>
# --------------------------------------------------------------------------
class LineNumberGutter(tk.Canvas):
    def __init__(self, master, text_widget, font, **kwargs):
        kwargs.setdefault("bg", COL_GUTTER_BG)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("width", 44)
        super().__init__(master, **kwargs)
        self.text_widget = text_widget
        self.font = font

    def redraw(self, *_args):
        self.delete("all")
        i = self.text_widget.index("@0,0")
        last_line = 1
        while True:
            dline = self.text_widget.dlineinfo(i)
            if dline is None:
                break
            y = dline[1]
            line_str = str(i).split(".")[0]
            last_line = int(line_str)
            self.create_text(
                self.winfo_width() - 6, y, anchor="ne",
                text=line_str, font=self.font, fill=COL_GUTTER_FG,
            )
            i = self.text_widget.index(f"{i}+1line")
        # Auto-grow gutter width for line-count digits.
        total_lines = int(self.text_widget.index("end-1c").split(".")[0])
        digits = max(2, len(str(total_lines)))
        needed = digits * 8 + 18
        if abs(int(self["width"]) - needed) > 4:
            self.config(width=needed)


# --------------------------------------------------------------------------
# Lightweight hover tooltip for tagged ranges inside a Text widget
# --------------------------------------------------------------------------
class TagTooltip:
    def __init__(self, text_widget, tag_name, message):
        self.text_widget = text_widget
        self.message = message
        self.tip = None
        text_widget.tag_bind(tag_name, "<Enter>", self._show)
        text_widget.tag_bind(tag_name, "<Leave>", self._hide)

    def _show(self, event):
        self._hide()
        x = event.x_root + 12
        y = event.y_root + 12
        self.tip = tk.Toplevel(self.text_widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            self.tip, text=self.message, justify="left",
            background="#3a1414", foreground="#ffd0d0",
            relief="solid", borderwidth=1, font=UI_FONT,
            padx=6, pady=3, wraplength=320,
        )
        lbl.pack()

    def _hide(self, _event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


# --------------------------------------------------------------------------
# Output console
# --------------------------------------------------------------------------
class OutputConsole(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        font = pick_font(EDITOR_FONT, EDITOR_FONT_FALLBACK)
        self.text = tk.Text(
            self, bg=COL_CONSOLE_BG, fg=COL_EDITOR_FG, insertbackground=COL_EDITOR_FG,
            font=font, wrap="word", state="disabled", borderwidth=0,
            highlightthickness=0, padx=8, pady=6,
        )
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=yscroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.text.tag_configure("stdout", foreground=COL_EDITOR_FG)
        self.text.tag_configure("info", foreground=COL_INFO)
        self.text.tag_configure("success", foreground=COL_SUCCESS)
        self.text.tag_configure("error", foreground=COL_ERROR)
        self.text.tag_configure("warning", foreground=COL_WARN)
        self.text.tag_configure(
            "memory_error", foreground=COL_ERROR, background=COL_CRITICAL_BG,
            underline=True,
        )
        self._tooltip = TagTooltip(self.text, "memory_error", MEMORY_ERROR_TOOLTIP)

    def write(self, line, tag="stdout"):
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", tag)
        self.text.configure(state="disabled")
        self.text.see("end")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


# --------------------------------------------------------------------------
# Settings dialog
# --------------------------------------------------------------------------
class SettingsDialog(tk.Toplevel):
    def __init__(self, master, cfg, on_save):
        super().__init__(master)
        self.title("Tool Paths & Settings")
        self.configure(bg=COL_PANEL)
        self.resizable(False, False)
        self.cfg = cfg
        self.on_save = on_save
        self.vars = {}

        fields = [
            ("mrbc_path", "mrbc.exe (compiler)", True),
            ("simulator_path", "simulator.exe", True),
            ("mrbwrite_path", "mrbwrite.exe (flash tool)", True),
        ]
        pad = {"padx": 10, "pady": 6}
        row = 0
        for key, label, browse in fields:
            tk.Label(self, text=label, bg=COL_PANEL, fg=COL_EDITOR_FG, font=UI_FONT).grid(
                row=row, column=0, sticky="w", **pad
            )
            var = tk.StringVar(value=cfg.get(key, ""))
            self.vars[key] = var
            entry = ttk.Entry(self, textvariable=var, width=46)
            entry.grid(row=row, column=1, sticky="we", **pad)
            if browse:
                btn = ttk.Button(self, text="Browse…", command=lambda k=key: self._browse(k))
                btn.grid(row=row, column=2, **pad)
            row += 1

        tk.Label(self, text="Flash baud rate", bg=COL_PANEL, fg=COL_EDITOR_FG, font=UI_FONT).grid(
            row=row, column=0, sticky="w", **pad
        )
        self.baud_var = tk.StringVar(value=cfg.get("baud_rate", "19200"))
        baud_box = ttk.Combobox(self, textvariable=self.baud_var, values=BAUD_RATES, width=12)
        baud_box.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        btn_frame = tk.Frame(self, bg=COL_PANEL)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(8, 10))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)

        self.grab_set()
        self.transient(master)

    def _browse(self, key):
        path = filedialog.askopenfilename(
            title="Select executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.vars[key].set(path)

    def _save(self):
        for key, var in self.vars.items():
            self.cfg[key] = var.get().strip()
        self.cfg["baud_rate"] = self.baud_var.get().strip() or "19200"
        save_config(self.cfg)
        self.on_save(self.cfg)
        self.destroy()


# --------------------------------------------------------------------------
# Main application
# --------------------------------------------------------------------------
class MrubycWorkbench(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.title(APP_TITLE)
        self.geometry(self.cfg.get("window_geometry", "1180x760"))
        self.configure(bg=COL_BG)
        self.minsize(820, 520)

        self.current_path = None
        self.dirty = False
        self.task_running = False
        self._running_proc = None   # subprocess handle so Stop can kill it
        self._highlight_job = None
        self._task_queue = queue.Queue()

        self.editor_font = pick_font(EDITOR_FONT, EDITOR_FONT_FALLBACK)
        self.ui_font = pick_font(UI_FONT, UI_FONT_FALLBACK)

        self._build_style()
        self._build_menu()
        self._build_toolbar()
        self._build_main_panes()
        self._build_statusbar()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<Control-n>", lambda e: self.new_file())
        self.bind_all("<Control-o>", lambda e: self.open_file())
        self.bind_all("<Control-s>", lambda e: self.save_file())

        last_file = self.cfg.get("last_file", "")
        if last_file and os.path.isfile(last_file):
            self._load_file(last_file)
        else:
            self.update_title()

        self.refresh_com_ports(silent=True)
        self.after(80, self._on_change)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COL_PANEL)
        style.configure("Toolbar.TButton", background=COL_PANEL, foreground=COL_EDITOR_FG,
                         font=self.ui_font, padding=6)
        style.map("Toolbar.TButton", background=[("active", COL_ACCENT_DIM)])
        style.configure("TLabel", background=COL_PANEL, foreground=COL_EDITOR_FG, font=self.ui_font)
        style.configure("TCombobox", padding=3)
        style.configure("Status.TLabel", background=COL_PANEL, foreground=COL_TEXT_MUTED,
                         font=self.ui_font)

    def _build_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self.new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="Open…", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As…", command=self.save_file_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Tool Paths & Settings…", command=self.open_settings)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        self.config(menu=menubar)

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=COL_PANEL)
        bar.pack(side="top", fill="x")

        def add_btn(text, cmd):
            b = ttk.Button(bar, text=text, style="Toolbar.TButton", command=cmd)
            b.pack(side="left", padx=(8 if text == "New" else 2, 2), pady=6)
            return b

        add_btn("New", self.new_file)
        add_btn("Open", self.open_file)
        add_btn("Save", self.save_file)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6, pady=6)
        self.btn_compile = add_btn("Compile", self.compile_file)
        self.btn_run = add_btn("Run in Simulator", self.run_simulator)
        self.btn_flash = add_btn("Flash to Hardware", self.flash_to_hardware)
        self.btn_stop = add_btn("⏹ Stop", self.stop_task)
        self.btn_stop.configure(state="disabled")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6, pady=6)
        add_btn("Settings", self.open_settings)

        # Right-aligned serial controls
        right = tk.Frame(bar, bg=COL_PANEL)
        right.pack(side="right", padx=8)

        ttk.Label(right, text="Baud").pack(side="left", padx=(0, 4))
        self.baud_var = tk.StringVar(value=self.cfg.get("baud_rate", "19200"))
        baud_box = ttk.Combobox(right, textvariable=self.baud_var, values=BAUD_RATES, width=8)
        baud_box.pack(side="left", padx=(0, 10))

        ttk.Label(right, text="Port").pack(side="left", padx=(0, 4))
        self.port_var = tk.StringVar(value=self.cfg.get("last_com_port", ""))
        self.port_box = ttk.Combobox(right, textvariable=self.port_var, width=16)
        self.port_box.pack(side="left", padx=(0, 4))
        ttk.Button(right, text="⟳", width=3, style="Toolbar.TButton",
                   command=lambda: self.refresh_com_ports(silent=False)).pack(side="left")

    def _build_main_panes(self):
        paned = tk.PanedWindow(self, orient="vertical", bg=COL_BORDER, sashwidth=5,
                                sashrelief="flat", borderwidth=0)
        paned.pack(side="top", fill="both", expand=True)

        editor_frame = tk.Frame(paned, bg=COL_EDITOR_BG)
        self.editor = CustomText(
            editor_frame, bg=COL_EDITOR_BG, fg=COL_EDITOR_FG, insertbackground=COL_EDITOR_FG,
            font=self.editor_font, wrap="none", undo=True, borderwidth=0,
            highlightthickness=0, padx=8, pady=6, tabs=self._tabstops(),
        )
        self.gutter = LineNumberGutter(editor_frame, self.editor, self.ui_font)
        yscroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self._editor_yview)
        xscroll = ttk.Scrollbar(editor_frame, orient="horizontal", command=self.editor.xview)
        self.editor.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.gutter.grid(row=0, column=0, sticky="ns")
        self.editor.grid(row=0, column=1, sticky="nsew")
        yscroll.grid(row=0, column=2, sticky="ns")
        xscroll.grid(row=1, column=1, sticky="ew")
        editor_frame.grid_rowconfigure(0, weight=1)
        editor_frame.grid_columnconfigure(1, weight=1)

        self.editor.tag_configure("error_line", background=COL_ERROR_LINE_BG)
        self.editor.bind("<<Change>>", self._on_change)
        self.editor.bind("<Configure>", self._on_change)
        self.editor.bind("<KeyRelease>", self._on_key)

        console_frame = tk.Frame(paned, bg=COL_PANEL)
        console_label = tk.Label(console_frame, text="Output", bg=COL_PANEL, fg=COL_TEXT_MUTED,
                                  font=self.ui_font, anchor="w")
        console_label.pack(side="top", fill="x", padx=8, pady=(4, 0))
        self.console = OutputConsole(console_frame)
        self.console.pack(side="top", fill="both", expand=True, padx=0, pady=(2, 0))

        paned.add(editor_frame, stretch="always")
        paned.add(console_frame, height=220)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=COL_PANEL)
        bar.pack(side="bottom", fill="x")
        self.status_path_var = tk.StringVar(value="Untitled")
        self.status_action_var = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status_path_var, style="Status.TLabel").pack(
            side="left", padx=10, pady=3
        )
        ttk.Label(bar, textvariable=self.status_action_var, style="Status.TLabel").pack(
            side="right", padx=10, pady=3
        )

    def _tabstops(self):
        # Tk wants tab stops in screen units; approximate 2 spaces.
        try:
            f = self.editor_font
        except AttributeError:
            f = EDITOR_FONT
        return None  # let Tk use its default; avoids font-metric edge cases

    def _editor_yview(self, *args):
        self.editor.yview(*args)
        self.gutter.redraw()

    # ------------------------------------------------------------------
    # Change tracking / highlighting
    # ------------------------------------------------------------------
    def _on_change(self, _event=None):
        self.gutter.redraw()
        self._schedule_highlight()

    def _on_key(self, _event=None):
        if not self.dirty:
            self.dirty = True
            self.update_title()
        self._schedule_highlight()

    def _schedule_highlight(self):
        if self._highlight_job is not None:
            try:
                self.after_cancel(self._highlight_job)
            except ValueError:
                pass
        self._highlight_job = self.after(150, self._do_highlight)

    def _do_highlight(self):
        self._highlight_job = None
        text = self.editor.get("1.0", "end-1c")
        for tag in _TAG_COLORS:
            self.editor.tag_remove(tag, "1.0", "end")
        for match in _TOKEN_RE.finditer(text):
            kind = match.lastgroup
            start, end = match.span()
            self.editor.tag_add(kind, f"1.0+{start}c", f"1.0+{end}c")
        for tag, color in _TAG_COLORS.items():
            self.editor.tag_configure(tag, foreground=color)
        # Keep error-line backgrounds visible above syntax foreground colors.
        self.editor.tag_raise("error_line")

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def update_title(self):
        name = self.current_path or "Untitled"
        star = "*" if self.dirty else ""
        self.title(f"{star}{os.path.basename(name)} — {APP_TITLE}")
        self.status_path_var.set(f"{name}{star}")

    def _confirm_discard_changes(self):
        if not self.dirty:
            return True
        result = messagebox.askyesnocancel(
            APP_TITLE, "Save changes to the current file before continuing?"
        )
        if result is None:
            return False
        if result:
            return self.save_file()
        return True

    def new_file(self):
        if not self._confirm_discard_changes():
            return
        self.editor.delete("1.0", "end")
        self.current_path = None
        self.dirty = False
        self.console.clear()
        self.update_title()
        self.set_status("New file")

    def open_file(self):
        if not self._confirm_discard_changes():
            return
        path = filedialog.askopenfilename(
            title="Open Ruby source",
            filetypes=[("Ruby source", "*.rb"), ("All files", "*.*")],
        )
        if path:
            self._load_file(path)

    def _load_file(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"Could not open file:\n{e}")
            return
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)
        self.current_path = path
        self.dirty = False
        self.cfg["last_file"] = path
        save_config(self.cfg)
        self.update_title()
        self._on_change()
        self.set_status(f"Opened {os.path.basename(path)}")

    def save_file(self):
        if self.current_path is None:
            return self.save_file_as()
        return self._write_file(self.current_path)

    def save_file_as(self):
        path = filedialog.asksaveasfilename(
            title="Save Ruby source",
            defaultextension=".rb",
            filetypes=[("Ruby source", "*.rb"), ("All files", "*.*")],
        )
        if not path:
            return False
        return self._write_file(path)

    def _write_file(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.get("1.0", "end-1c"))
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"Could not save file:\n{e}")
            return False
        self.current_path = path
        self.dirty = False
        self.cfg["last_file"] = path
        save_config(self.cfg)
        self.update_title()
        self.set_status(f"Saved {os.path.basename(path)}")
        return True

    def set_status(self, text):
        self.status_action_var.set(text)

    # ------------------------------------------------------------------
    # Error-line highlighting
    # ------------------------------------------------------------------
    def clear_error_highlights(self):
        self.editor.tag_remove("error_line", "1.0", "end")

    def highlight_error_line(self, line_no):
        line_no = max(1, line_no)
        self.editor.tag_add("error_line", f"{line_no}.0", f"{line_no}.0 lineend+1c")
        self.editor.see(f"{line_no}.0")
        self.editor.mark_set("insert", f"{line_no}.0")

    # ------------------------------------------------------------------
    # Generic background task runner (thread + queue + after-poll)
    # ------------------------------------------------------------------
    def _run_task(self, cmd, cwd, on_line, on_done, busy_label):
        if self.task_running:
            messagebox.showinfo(APP_TITLE, "Another action is already running. Please wait.")
            return
        self.task_running = True
        self._set_buttons_enabled(False)
        self.set_status(busy_label)
        q = queue.Queue()

        def worker():
            try:
                env = os.environ.copy()
                if os.name == "nt":
                    ucrt64_bin = "C:\\msys64\\ucrt64\\bin"
                    if ucrt64_bin not in env.get("PATH", ""):
                        env["PATH"] = ucrt64_bin + os.pathsep + env.get("PATH", "")
                kwargs = dict(
                    cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, env=env,
                )
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                proc = subprocess.Popen(cmd, **kwargs)
                self._running_proc = proc
            except FileNotFoundError:
                q.put(("error", f"Executable not found: {cmd[0]}\n"
                                 f"Check the path in Tools > Settings."))
                q.put(("done", -1))
                return
            except OSError as e:
                q.put(("error", f"Could not launch process: {e}"))
                q.put(("done", -1))
                return

            try:
                # Read output live while the process is running.
                reader_done = threading.Event()
                output_lines = []

                def reader():
                    try:
                        while True:
                            raw_line = proc.stdout.readline()
                            if raw_line == "":
                                break
                            line = raw_line.rstrip("\r\n")
                            output_lines.append(line)
                            q.put(("line", line))
                    except Exception as e:
                        q.put(("error", f"Error reading process output: {e}"))
                    finally:
                        reader_done.set()

                reader_thread = threading.Thread(target=reader, daemon=True)
                reader_thread.start()

                returncode = proc.wait()
                reader_done.wait(timeout=0.5)

                # Fallback: if any output remains in the pipe, read it now.
                try:
                    remainder = proc.stdout.read()
                    if remainder:
                        for raw_line in remainder.splitlines():
                            line = raw_line.rstrip("\r\n")
                            if line not in output_lines:
                                q.put(("line", line))
                except Exception:
                    pass

                q.put(("done", returncode))
            except Exception as e:
                q.put(("error", str(e)))
                q.put(("done", -1))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "line":
                        on_line(payload)
                    elif kind == "error":
                        on_line(payload, tag="error")
                    elif kind == "done":
                        self.task_running = False
                        self._running_proc = None
                        self._set_buttons_enabled(True)
                        on_done(payload)
                        return
            except queue.Empty:
                pass
            self.after(40, poll)

        self.after(40, poll)

    def _set_buttons_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        stop_state = "disabled" if enabled else "normal"
        for b in (self.btn_compile, self.btn_run, self.btn_flash):
            b.configure(state=state)
        self.btn_stop.configure(state=stop_state)

    def stop_task(self):
        """Kill the currently running subprocess and re-enable the toolbar."""
        proc = self._running_proc
        if proc is None:
            return
        try:
            proc.terminate()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self.console.write("Task stopped by user.", tag="warning")
        self.set_status("Stopped")
        # poll() will see the process exit and clean up task_running / buttons.

    # ------------------------------------------------------------------
    # Compile
    # ------------------------------------------------------------------
    def compile_file(self):
        if self.current_path is None or self.dirty:
            if not self.save_file():
                return
        path = self.current_path
        mrbc = self.cfg.get("mrbc_path", "")
        if not mrbc:
            messagebox.showwarning(APP_TITLE, "Set the mrbc.exe path in Tools > Settings first.")
            return

        self.clear_error_highlights()
        self.console.clear()
        self.console.write(f"$ {mrbc} {path}", tag="info")

        error_lines_found = []

        def on_line(line, tag=None):
            if tag is None:
                m = _MRBC_ERROR_RE.match(line)
                if m:
                    tag = "error"
                    try:
                        error_lines_found.append(int(m.group(2)))
                    except ValueError:
                        pass
                else:
                    gm = _GENERIC_LINE_RE.search(line)
                    if gm:
                        tag = "error"
                        try:
                            error_lines_found.append(int(gm.group(1)))
                        except ValueError:
                            pass
                    else:
                        tag = "stdout"
            self.console.write(line, tag=tag)

        def on_done(returncode):
            mrb_path = self._mrb_path_for(path)
            if returncode == 0 and os.path.isfile(mrb_path):
                self.console.write(f"Compiled successfully -> {os.path.basename(mrb_path)}", tag="success")
                self.set_status("Compile succeeded")
            else:
                self.console.write(f"Compile failed (exit code {returncode}).", tag="error")
                self.set_status("Compile failed")
                for ln in error_lines_found:
                    self.highlight_error_line(ln)

        self._run_task([mrbc, path], os.path.dirname(path) or ".", on_line, on_done, "Compiling…")

    def _mrb_path_for(self, rb_path):
        base, _ext = os.path.splitext(rb_path)
        return base + ".mrb"

    # ------------------------------------------------------------------
    # Run in simulator
    # ------------------------------------------------------------------
    def run_simulator(self):
        if self.current_path is None:
            messagebox.showwarning(APP_TITLE, "Save and compile a file first.")
            return
        mrb_path = self._mrb_path_for(self.current_path)
        if not os.path.isfile(mrb_path):
            messagebox.showwarning(
                APP_TITLE, "No compiled .mrb file found.\nClick Compile first."
            )
            return
        simulator = self.cfg.get("simulator_path", "")
        if not simulator:
            messagebox.showwarning(APP_TITLE, "Set the simulator.exe path in Tools > Settings first.")
            return

        self.console.clear()
        self.console.write(
            "Running simulator and capturing output in this editor console...",
            tag="info",
        )

        def on_line(line, tag=None):
            if tag is None:
                tag = "stdout"
                for pattern in MEMORY_ERROR_PATTERNS:
                    if pattern in line:
                        tag = "memory_error"
                        break
                else:
                    low = line.lower()
                    if "error" in low or "reset" in low:
                        tag = "warning"
            self.console.write(line, tag=tag)

        def on_done(returncode):
            self.console.write(
                f"Simulator process exited (code {returncode}).",
                tag="success" if returncode == 0 else "warning",
            )
            self.set_status("Simulation finished")

        self._run_task([simulator, mrb_path], os.path.dirname(mrb_path) or ".",
                        on_line, on_done, "Running in simulator…")

    # ------------------------------------------------------------------
    # Flash to hardware
    # ------------------------------------------------------------------
    def flash_to_hardware(self):
        if self.current_path is None:
            messagebox.showwarning(APP_TITLE, "Save and compile a file first.")
            return
        mrb_path = self._mrb_path_for(self.current_path)
        if not os.path.isfile(mrb_path):
            messagebox.showwarning(
                APP_TITLE, "No compiled .mrb file found.\nClick Compile first."
            )
            return
        mrbwrite = self.cfg.get("mrbwrite_path", "")
        if not mrbwrite or not os.path.isfile(mrbwrite):
            msg = (
                f"mrbwrite not found at:\n  {mrbwrite or '(not configured)'}\n\n"
                "Build it first (requires Qt6 + QtSerialPort):\n"
                "  qmake && make\n\n"
                "Then set the path in Tools > Settings."
            )
            messagebox.showwarning(APP_TITLE, msg)
            return
        port = self._normalize_com_port(self.port_var.get().strip())
        if not port:
            messagebox.showwarning(APP_TITLE, "Select or type a COM port first.")
            return
        baud = self.baud_var.get().strip() or "19200"

        if not messagebox.askyesno(
            APP_TITLE, f"Flash {os.path.basename(mrb_path)} to the board on {port}?"
        ):
            return

        self.cfg["last_com_port"] = self.port_var.get().strip()  # save original user value
        self.cfg["baud_rate"] = baud
        save_config(self.cfg)

        cmd = [mrbwrite, "-l", port, "-s", baud, mrb_path]
        self.console.clear()
        self.console.write(f"$ {' '.join(cmd)}", tag="info")

        # mrbwrite exits 0 even on failure (serial port not found, etc.).
        # Track whether any error line was seen so on_done can override.
        _saw_error = [False]
        _MRBWRITE_ERROR_PATTERNS = [
            "can't open", "cannot open", "failed to open",
            "no such", "-err", "error", "timed out", "timeout",
        ]

        def on_line(line, tag=None):
            if tag is None:
                low = line.lower()
                if any(p in low for p in _MRBWRITE_ERROR_PATTERNS):
                    tag = "error"
                    _saw_error[0] = True
                elif line.startswith("+"):
                    tag = "success"
                else:
                    tag = "stdout"
            self.console.write(line, tag=tag)

        def on_done(returncode):
            failed = (returncode != 0) or _saw_error[0]
            if failed:
                self.console.write("Flash failed — check the port and baud rate.", tag="error")
                self.set_status("Flash failed")
            else:
                self.console.write("Flash complete.", tag="success")
                self.set_status("Flash succeeded")

        self._run_task(cmd, os.path.dirname(mrb_path) or ".", on_line, on_done, "Flashing…")

    # ------------------------------------------------------------------
    # Serial port discovery
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_com_port(port):
        """Accept '3' or 'COM3'; return 'COM3' on Windows, unchanged elsewhere.
        Also upgrades COM10+ to the \\\\.\\ long form that some tools require."""
        if os.name != "nt":
            return port
        # Bare number → COM<n>
        if re.match(r"^\d+$", port):
            port = f"COM{port}"
        # High-numbered port → long device path
        m = re.match(r"^(COM)(\d+)$", port, re.IGNORECASE)
        if m and int(m.group(2)) >= 10:
            port = f"\\\\.\\{port.upper()}"
        return port

    def refresh_com_ports(self, silent=True):
        ports = []
        if _serial_list_ports is not None:
            try:
                ports = [p.device for p in _serial_list_ports.comports()]
            except Exception:
                ports = []
        if not ports:
            mrbwrite = self.cfg.get("mrbwrite_path", "")
            if mrbwrite and os.path.isfile(mrbwrite):
                try:
                    env = os.environ.copy()
                    if os.name == "nt":
                        ucrt64_bin = "C:\\msys64\\ucrt64\\bin"
                        if ucrt64_bin not in env.get("PATH", ""):
                            env["PATH"] = ucrt64_bin + os.pathsep + env.get("PATH", "")
                    kwargs = {"env": env}
                    if os.name == "nt":
                        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                    result = subprocess.run(
                        [mrbwrite, "--showline"], capture_output=True, text=True,
                        timeout=5, **kwargs,
                    )
                    ports = self._parse_showline(result.stdout)
                except Exception:
                    ports = []
        self.port_box["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])
        if not silent:
            if ports:
                self.set_status(f"Found {len(ports)} serial port(s)")
            else:
                self.set_status("No serial ports found — you can type one manually")

    @staticmethod
    def _parse_showline(output):
        found = []
        for raw in output.splitlines():
            line = raw.strip()
            if not line:
                continue
            # Heuristic: a "port line" usually looks like a bare device
            # name (COM3, /dev/ttyUSB0, cu.usbserial-XXXX) optionally
            # followed by a description. Take the first whitespace token.
            token = line.split()[0]
            if re.match(r"^(COM\d+|/dev/\S+|cu\.\S+|tty\.\S+)$", token, re.IGNORECASE):
                found.append(token)
        return found

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def open_settings(self):
        SettingsDialog(self, self.cfg, self._on_settings_saved)

    def _on_settings_saved(self, cfg):
        self.cfg = cfg
        self.baud_var.set(cfg.get("baud_rate", "19200"))
        self.set_status("Settings saved")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def on_close(self):
        if not self._confirm_discard_changes():
            return
        self.cfg["window_geometry"] = self.geometry()
        self.cfg["baud_rate"] = self.baud_var.get().strip() or "19200"
        self.cfg["last_com_port"] = self.port_var.get().strip()
        save_config(self.cfg)
        self.destroy()


def main():
    app = MrubycWorkbench()
    app.mainloop()


if __name__ == "__main__":
    main()
