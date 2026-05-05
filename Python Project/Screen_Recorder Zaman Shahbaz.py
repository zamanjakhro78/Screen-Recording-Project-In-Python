"""
╔══════════════════════════════════════════════════════════╗
║         SMART SCREEN RECORDER – Python Desktop App       ║
║         Modern Dark UI · MP4 Export · Audio Support      ║
║         AUTO-INSTALLS missing libraries on first run     ║
╚══════════════════════════════════════════════════════════╝

Just run:
    python screen_recorder.py
All missing libraries will be installed automatically!
"""

# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1 ── AUTO-INSTALLER  (runs before anything else)
# ══════════════════════════════════════════════════════════════════════════════
import sys
import subprocess
import importlib

# Map: pip package name  ->  import name
REQUIRED = {
    "opencv-python"   : "cv2",
    "numpy"           : "numpy",
    "pyautogui"       : "pyautogui",
    "pillow"          : "PIL",
    "keyboard"        : "keyboard",
}


def _install(pkg):
    """pip install pkg silently, return True on success."""
    print(f"[AutoInstall] Installing {pkg} ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def _ensure_deps():
    missing = []
    for pip_name, import_name in REQUIRED.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        return  # Nothing to do

    # Show a tiny splash so the user knows what is happening
    import tkinter as _tk
    splash = _tk.Tk()
    splash.title("Smart Screen Recorder - First-Time Setup")
    splash.geometry("460x150")
    splash.configure(bg="#1e1e2f")
    splash.resizable(False, False)

    _tk.Label(splash, text="Installing required libraries...",
              bg="#1e1e2f", fg="#ffffff",
              font=("Segoe UI", 12, "bold")).pack(pady=(20, 4))
    prog_lbl = _tk.Label(splash, text="", bg="#1e1e2f", fg="#ffa500",
                         font=("Segoe UI", 10))
    prog_lbl.pack()
    splash.update()

    failed = []
    for pkg in missing:
        prog_lbl.config(text=f"pip install {pkg} ...")
        splash.update()
        ok = _install(pkg)
        if not ok:
            failed.append(pkg)

    # pyaudio - try plain pip, then pipwin on Windows as fallback
    try:
        importlib.import_module("pyaudio")
    except ImportError:
        prog_lbl.config(text="pip install pyaudio ...")
        splash.update()
        ok = _install("pyaudio")
        if not ok and sys.platform == "win32":
            prog_lbl.config(text="Trying pipwin for pyaudio ...")
            splash.update()
            _install("pipwin")
            subprocess.run(
                [sys.executable, "-m", "pipwin", "install", "pyaudio", "--quiet"],
                capture_output=True
            )

    splash.destroy()

    if failed:
        import tkinter.messagebox as _mb
        _mb.showwarning(
            "Install Warning",
            f"Could not auto-install:\n  {', '.join(failed)}\n\n"
            "Run manually in your terminal:\n"
            f"  pip install {' '.join(failed)}\n\n"
            "The app will open in limited mode."
        )


_ensure_deps()   # <- runs BEFORE the heavy imports below

# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2 ── NORMAL IMPORTS  (safe now after auto-install)
# ══════════════════════════════════════════════════════════════════════════════
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import datetime
import os
import wave
import tempfile

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    import numpy as np
    NP_OK = True
except ImportError:
    NP_OK = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

try:
    import pyaudio
    PYAUDIO_OK = True
except ImportError:
    PYAUDIO_OK = False

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import keyboard
    KEYBOARD_OK = True
except ImportError:
    KEYBOARD_OK = False

# ══════════════════════════════════════════════════════════════════════════════
#  COLOUR PALETTE
# ══════════════════════════════════════════════════════════════════════════════
BG        = "#1e1e2f"
PANEL     = "#2a2a3d"
PANEL2    = "#23233a"
START_CLR = "#ff4d4d"
STOP_CLR  = "#cc1a1a"
PAUSE_CLR = "#ffa500"
GREEN     = "#4caf50"
WHITE     = "#ffffff"
GREY      = "#888899"
ACCENT    = "#7b61ff"
BORDER    = "#3a3a55"

# ══════════════════════════════════════════════════════════════════════════════
#  AUDIO RECORDER
# ══════════════════════════════════════════════════════════════════════════════
class AudioRecorder:
    CHUNK = 1024
    CHAN  = 1
    RATE  = 44100

    def __init__(self):
        self.pa      = None
        self.stream  = None
        self.frames  = []
        self._active = False
        self._paused = False
        self.tmpfile = None
        self.enabled = PYAUDIO_OK

    def start(self):
        if not self.enabled:
            return
        self.frames  = []
        self._active = True
        self._paused = False
        try:
            self.pa     = pyaudio.PyAudio()
            self.stream = self.pa.open(
                format=pyaudio.paInt16, channels=self.CHAN,
                rate=self.RATE, input=True,
                frames_per_buffer=self.CHUNK
            )
            threading.Thread(target=self._loop, daemon=True).start()
        except Exception as e:
            print(f"[Audio] Mic error: {e}")
            self.enabled = False

    def _loop(self):
        while self._active:
            if not self._paused:
                try:
                    data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                    self.frames.append(data)
                except Exception:
                    break
            else:
                time.sleep(0.05)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._active = False
        time.sleep(0.15)
        for obj in (self.stream, self.pa):
            if obj is None:
                continue
            try:
                if hasattr(obj, "stop_stream"):  obj.stop_stream()
                if hasattr(obj, "close"):         obj.close()
                if hasattr(obj, "terminate"):     obj.terminate()
            except Exception:
                pass

    def save_wav(self):
        if not self.frames:
            return None
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(self.CHAN)
            wf.setsampwidth(2)
            wf.setframerate(self.RATE)
            wf.writeframes(b"".join(self.frames))
        self.tmpfile = path
        return path


# ══════════════════════════════════════════════════════════════════════════════
#  VIDEO RECORDER
# ══════════════════════════════════════════════════════════════════════════════
class VideoRecorder:
    def __init__(self, fps=30, quality="High", save_path="", region=None):
        self.fps        = fps
        self.quality    = quality
        self.save_path  = save_path
        self.region     = region
        self._active    = False
        self._paused    = False
        self.out        = None
        self.tmp_video  = None
        self.frame_size = None

    def _tmp_path(self):
        fd, path = tempfile.mkstemp(suffix=".avi")
        os.close(fd)
        self.tmp_video = path
        return path

    def _screen_size(self):
        if self.region:
            return (self.region[2], self.region[3])
        s = pyautogui.size()
        return (s.width, s.height)

    def _grab(self):
        img = pyautogui.screenshot(region=self.region)
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def start(self):
        if not (CV2_OK and NP_OK and PYAUTOGUI_OK):
            return False
        self.frame_size = self._screen_size()
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        self.out = cv2.VideoWriter(
            self._tmp_path(), fourcc, self.fps, self.frame_size
        )
        self._active = True
        self._paused = False
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def _loop(self):
        interval = 1.0 / self.fps
        while self._active:
            t0 = time.time()
            if not self._paused:
                frame = self._grab()
                if frame is not None:
                    frame = cv2.resize(frame, self.frame_size)
                    self.out.write(frame)
            gap = interval - (time.time() - t0)
            if gap > 0:
                time.sleep(gap)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._active = False
        time.sleep(0.35)
        if self.out:
            self.out.release()

    def merge_and_save(self, wav_path=None):
        final = self.save_path
        if not final.endswith(".mp4"):
            final += ".mp4"

        if wav_path and os.path.exists(wav_path):
            cmd = (
                f'ffmpeg -y -i "{self.tmp_video}" -i "{wav_path}" '
                f'-c:v copy -c:a aac -strict experimental '
                f'"{final}" -loglevel quiet'
            )
            ret = os.system(cmd)
            if ret != 0:
                import shutil
                shutil.copy(self.tmp_video, final)
        else:
            import shutil
            shutil.copy(self.tmp_video, final)

        for f in [self.tmp_video, wav_path]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        return final


# ══════════════════════════════════════════════════════════════════════════════
#  SETTINGS WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.cfg = cfg
        self.title("Advanced Settings")
        self.geometry("400x460")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.grab_set()
        self._build()

    def _lbl(self, p, txt, size=10, fg=WHITE):
        return tk.Label(p, text=txt, bg=PANEL, fg=fg,
                        font=("Segoe UI", size))

    def _sep(self, p):
        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=8)

    def _row(self, p, label, widget_fn):
        r = tk.Frame(p, bg=PANEL)
        r.pack(fill="x", pady=4)
        self._lbl(r, label).pack(side="left")
        widget_fn(r).pack(side="right")

    def _build(self):
        c = tk.Frame(self, bg=PANEL, padx=22, pady=18)
        c.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(c, text="Advanced Settings", bg=PANEL, fg=WHITE,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 10))
        self._sep(c)

        self.res  = tk.StringVar(value=self.cfg.get("resolution", "1920x1080"))
        self.fps  = tk.IntVar(value=self.cfg.get("fps", 30))
        self.qual = tk.StringVar(value=self.cfg.get("quality", "High"))
        self.aud  = tk.BooleanVar(value=self.cfg.get("audio", True))
        self.cd   = tk.BooleanVar(value=self.cfg.get("countdown", True))
        self.cur  = tk.BooleanVar(value=self.cfg.get("cursor_highlight", False))

        self._row(c, "Resolution", lambda p: ttk.Combobox(
            p, textvariable=self.res, width=13, state="readonly",
            values=["1280x720", "1920x1080", "2560x1440"]))
        self._row(c, "FPS", lambda p: ttk.Combobox(
            p, textvariable=self.fps, width=6, state="readonly",
            values=[15, 30, 60]))
        self._row(c, "Quality", lambda p: ttk.Combobox(
            p, textvariable=self.qual, width=10, state="readonly",
            values=["Low", "Medium", "High"]))
        self._sep(c)

        for lbl_text, var in [
            ("Microphone Recording", self.aud),
            ("Countdown 3...2...1", self.cd),
            ("Cursor Highlight FX",  self.cur),
        ]:
            self._row(c, lbl_text, lambda p, v=var: tk.Checkbutton(
                p, variable=v, bg=PANEL, fg=WHITE,
                selectcolor=ACCENT, activebackground=PANEL, cursor="hand2"))

        self._sep(c)
        tk.Label(c, text="Hotkeys:  F9 Start  |  F10 Stop  |  F11 Pause",
                 bg=PANEL, fg=GREY, font=("Segoe UI", 9)).pack(anchor="w")
        self._sep(c)
        tk.Button(c, text="Save & Close", bg=ACCENT, fg=WHITE,
                  font=("Segoe UI", 11, "bold"), relief="flat",
                  padx=18, pady=8, cursor="hand2",
                  command=self._save).pack(pady=(6, 0))

    def _save(self):
        self.cfg.update(
            resolution=self.res.get(), fps=self.fps.get(),
            quality=self.qual.get(), audio=self.aud.get(),
            countdown=self.cd.get(), cursor_highlight=self.cur.get()
        )
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class SmartScreenRecorder(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Smart Screen Recorder")
        self.geometry("800x580")
        self.minsize(720, 530)
        self.configure(bg=BG)

        self.app_state   = "idle"
        self.elapsed_sec = 0
        self._timer_job  = None
        self.vid_rec     = None
        self.aud_rec     = AudioRecorder()

        self.cfg = {
            "fps": 30, "quality": "High", "resolution": "1920x1080",
            "audio": True, "countdown": True, "cursor_highlight": False,
            "save_dir": os.path.expanduser("~/Videos"),
        }
        os.makedirs(self.cfg["save_dir"], exist_ok=True)

        self._style_ttk()
        self._build_header()
        self._build_body()
        self._build_footer()
        self._bind_hotkeys()
        self._refresh_dep_status()   # show status without popup

    # ─── TTK style ─────────────────────────────────────────────────────────────
    def _style_ttk(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TCombobox",
                    fieldbackground=PANEL2, background=PANEL2,
                    foreground=WHITE, selectbackground=ACCENT,
                    arrowcolor=WHITE, bordercolor=BORDER)

    # ─── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        h = tk.Frame(self, bg=PANEL, pady=13)
        h.pack(fill="x")
        tk.Label(h, text="  SMART SCREEN RECORDER",
                 bg=PANEL, fg=WHITE,
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=20)
        self.rec_badge = tk.Label(h, text="  REC ",
                                  bg=START_CLR, fg=WHITE,
                                  font=("Segoe UI", 9, "bold"),
                                  padx=6, pady=2)
        tk.Label(h, text="v1.0  Python",
                 bg=PANEL, fg=GREY,
                 font=("Segoe UI", 9)).pack(side="right", padx=20)

    # ─── Body ──────────────────────────────────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        self._build_left(body)
        self._build_right(body)

    # ─── Left panel ────────────────────────────────────────────────────────────
    def _build_left(self, parent):
        left = tk.Frame(parent, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=22, pady=18)

        # Timer card
        tc = tk.Frame(left, bg=PANEL, pady=22, padx=20)
        tc.pack(fill="x", pady=(0, 14))

        self.timer_lbl = tk.Label(tc, text="00:00:00",
                                  bg=PANEL, fg=WHITE,
                                  font=("Courier New", 46, "bold"))
        self.timer_lbl.pack()

        self.status_lbl = tk.Label(tc, text="  Ready to Record",
                                   bg=PANEL, fg=GREEN,
                                   font=("Segoe UI", 10))
        self.status_lbl.pack(pady=(5, 0))

        # Buttons
        bf = tk.Frame(left, bg=BG)
        bf.pack(fill="x", pady=(0, 10))

        self.btn_start = self._make_btn(
            bf, "   START   (F9)", START_CLR, self._on_start, h=54)
        self.btn_start.pack(fill="x", pady=(0, 8))

        row2 = tk.Frame(bf, bg=BG)
        row2.pack(fill="x")

        self.btn_pause = self._make_btn(
            row2, "  PAUSE  (F11)", PAUSE_CLR, self._on_pause, h=44)
        self.btn_pause.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.btn_pause.config(state="disabled")

        self.btn_stop = self._make_btn(
            row2, "  STOP  (F10)", STOP_CLR, self._on_stop, h=44)
        self.btn_stop.pack(side="right", expand=True, fill="x", padx=(5, 0))
        self.btn_stop.config(state="disabled")

        # Save location bar
        sc = tk.Frame(left, bg=PANEL, padx=12, pady=10)
        sc.pack(fill="x")
        tk.Label(sc, text="Save Location",
                 bg=PANEL, fg=GREY, font=("Segoe UI", 9)).pack(anchor="w")
        sr = tk.Frame(sc, bg=PANEL)
        sr.pack(fill="x", pady=(5, 0))
        self.save_var = tk.StringVar(value=self.cfg["save_dir"])
        tk.Entry(sr, textvariable=self.save_var,
                 bg=PANEL2, fg=WHITE, insertbackground=WHITE,
                 relief="flat", font=("Segoe UI", 9), bd=0
                 ).pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))
        self._make_btn(sr, "Browse", ACCENT, self._browse, h=30).pack(side="right")

    # ─── Right panel ───────────────────────────────────────────────────────────
    def _build_right(self, parent):
        right = tk.Frame(parent, bg=PANEL, width=210)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        def section(txt):
            tk.Label(right, text=txt, bg=PANEL, fg=GREY,
                     font=("Segoe UI", 8, "bold")).pack(
                         anchor="w", padx=16, pady=(14, 3))
            tk.Frame(right, bg=BORDER, height=1).pack(fill="x", padx=16)

        def lbl(txt):
            tk.Label(right, text=txt, bg=PANEL, fg=WHITE,
                     font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(8, 2))

        section("SETTINGS")

        lbl("FPS")
        self.fps_var = tk.IntVar(value=self.cfg["fps"])
        ttk.Combobox(right, textvariable=self.fps_var,
                     values=[15, 30, 60], width=14,
                     state="readonly").pack(padx=16, pady=(0, 4))

        lbl("Quality")
        self.qual_var = tk.StringVar(value=self.cfg["quality"])
        ttk.Combobox(right, textvariable=self.qual_var,
                     values=["Low", "Medium", "High"], width=14,
                     state="readonly").pack(padx=16, pady=(0, 8))

        tk.Frame(right, bg=BORDER, height=1).pack(fill="x", padx=16, pady=4)

        self.audio_var     = tk.BooleanVar(value=self.cfg["audio"])
        self.countdown_var = tk.BooleanVar(value=self.cfg["countdown"])
        self.cursor_var    = tk.BooleanVar(value=self.cfg["cursor_highlight"])

        for label, var in [
            ("Microphone",   self.audio_var),
            ("Countdown",    self.countdown_var),
            ("Cursor FX",    self.cursor_var),
        ]:
            row = tk.Frame(right, bg=PANEL)
            row.pack(fill="x", padx=16, pady=3)
            tk.Label(row, text=label, bg=PANEL, fg=WHITE,
                     font=("Segoe UI", 9)).pack(side="left")
            tk.Checkbutton(row, variable=var, bg=PANEL, fg=WHITE,
                           selectcolor=ACCENT, activebackground=PANEL,
                           cursor="hand2").pack(side="right")

        tk.Frame(right, bg=BORDER, height=1).pack(fill="x", padx=16, pady=8)
        self._make_btn(right, "Advanced Settings",
                       ACCENT, self._open_settings, h=36
                       ).pack(fill="x", padx=16, pady=(0, 8))

        section("LIBRARY STATUS")
        self.dep_frame = tk.Frame(right, bg=PANEL)
        self.dep_frame.pack(fill="x", padx=16, pady=(4, 0))

    # ─── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        f = tk.Frame(self, bg=PANEL2, pady=7)
        f.pack(fill="x", side="bottom")
        tk.Label(f,
                 text="Smart Screen Recorder  |  F9 Start  |  F10 Stop  |  F11 Pause/Resume",
                 bg=PANEL2, fg=GREY, font=("Segoe UI", 8)).pack()

    # ─── Dependency status (no popup) ──────────────────────────────────────────
    def _refresh_dep_status(self):
        for w in self.dep_frame.winfo_children():
            w.destroy()

        deps = [
            ("cv2",       CV2_OK),
            ("numpy",     NP_OK),
            ("pyautogui", PYAUTOGUI_OK),
            ("pyaudio",   PYAUDIO_OK),
            ("pillow",    PIL_OK),
        ]
        for name, ok in deps:
            c   = GREEN if ok else START_CLR
            sym = "OK" if ok else "X"
            tk.Label(self.dep_frame, text=f"  [{sym}]  {name}",
                     bg=PANEL, fg=c,
                     font=("Segoe UI", 9)).pack(anchor="w", pady=1)

        all_ok = all(ok for _, ok in deps)
        if all_ok:
            self.status_lbl.config(text="  Ready to Record", fg=GREEN)
        else:
            missing = [n for n, ok in deps if not ok]
            self.status_lbl.config(
                text=f"  Missing: {', '.join(missing)}", fg=PAUSE_CLR)

    # ─── Button helpers ────────────────────────────────────────────────────────
    def _make_btn(self, parent, text, colour, cmd, h=40):
        b = tk.Button(parent, text=text, bg=colour, fg=WHITE,
                      font=("Segoe UI", 11, "bold"),
                      activebackground=colour, activeforeground=WHITE,
                      relief="flat", bd=0, cursor="hand2",
                      pady=h // 14, command=cmd)

        def _on_enter(e):
            b.config(bg=self._lighten(colour, 25))

        def _on_leave(e):
            b.config(bg=colour)

        b.bind("<Enter>", _on_enter)
        b.bind("<Leave>", _on_leave)
        return b

    @staticmethod
    def _lighten(hex_c, amt):
        h = hex_c.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return "#{:02x}{:02x}{:02x}".format(
            min(255, r + amt), min(255, g + amt), min(255, b + amt))

    # ─── Hotkeys ───────────────────────────────────────────────────────────────
    def _bind_hotkeys(self):
        if not KEYBOARD_OK:
            return
        try:
            keyboard.add_hotkey("F9",  self._on_start,  suppress=True)
            keyboard.add_hotkey("F10", self._on_stop,   suppress=True)
            keyboard.add_hotkey("F11", self._on_pause,  suppress=True)
        except Exception:
            pass

    # ─── Config sync ───────────────────────────────────────────────────────────
    def _sync_cfg(self):
        self.cfg.update(
            fps=self.fps_var.get(),
            quality=self.qual_var.get(),
            audio=self.audio_var.get(),
            countdown=self.countdown_var.get(),
            cursor_highlight=self.cursor_var.get(),
            save_dir=self.save_var.get(),
        )

    def _browse(self):
        p = filedialog.askdirectory(
            title="Choose Save Location",
            initialdir=self.cfg["save_dir"])
        if p:
            self.cfg["save_dir"] = p
            self.save_var.set(p)

    def _open_settings(self):
        self._sync_cfg()
        SettingsWindow(self, self.cfg)

    # ─── Button state manager ──────────────────────────────────────────────────
    def _set_btn_states(self):
        idle = self.app_state == "idle"
        live = self.app_state in ("recording", "paused")
        self.btn_start.config(state="normal" if idle else "disabled")
        self.btn_pause.config(state="normal" if live  else "disabled")
        self.btn_stop.config( state="normal" if live  else "disabled")

    # ─── Timer ─────────────────────────────────────────────────────────────────
    def _start_timer(self):
        self._stop_timer()
        self._tick()

    def _tick(self):
        self.elapsed_sec += 1
        h = self.elapsed_sec // 3600
        m = (self.elapsed_sec % 3600) // 60
        s = self.elapsed_sec % 60
        self.timer_lbl.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        self._timer_job = self.after(1000, self._tick)

    def _stop_timer(self):
        if self._timer_job:
            self.after_cancel(self._timer_job)
            self._timer_job = None

    # ─── REC badge blink ───────────────────────────────────────────────────────
    def _blink(self):
        if self.app_state != "recording":
            self.rec_badge.place_forget()
            return
        if self.rec_badge.place_info():
            self.rec_badge.place_forget()
        else:
            self.rec_badge.place(x=8, y=8)
        self.after(700, self._blink)

    # ══════════════════════════════════════════════════════════════════════════
    #  RECORDING ACTIONS
    # ══════════════════════════════════════════════════════════════════════════
    def _on_start(self):
        if self.app_state != "idle":
            return
        self._sync_cfg()
        if self.cfg["countdown"]:
            self.app_state = "countdown"
            self._set_btn_states()
            threading.Thread(target=self._countdown_then_record,
                             daemon=True).start()
        else:
            self._begin()

    def _countdown_then_record(self):
        for n in [3, 2, 1]:
            self.after(0, lambda n=n: (
                self.status_lbl.config(text=f"  Starting in  {n}...",
                                       fg=PAUSE_CLR),
                self.timer_lbl.config(text=f"00:00:0{n}")
            ))
            time.sleep(1)
        self.after(0, self._begin)

    def _begin(self):
        if not (CV2_OK and NP_OK and PYAUTOGUI_OK):
            missing = []
            if not CV2_OK:       missing.append("opencv-python")
            if not NP_OK:        missing.append("numpy")
            if not PYAUTOGUI_OK: missing.append("pyautogui")
            messagebox.showerror(
                "Cannot Record",
                f"Still missing after auto-install:\n  {', '.join(missing)}\n\n"
                "Please run manually in terminal:\n"
                f"  pip install {' '.join(missing)}\n\n"
                "Then restart the app."
            )
            self.app_state = "idle"
            self._set_btn_states()
            return

        ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fpath = os.path.join(self.cfg["save_dir"], f"Recording_{ts}.mp4")

        self.vid_rec = VideoRecorder(
            fps=self.cfg["fps"],
            quality=self.cfg["quality"],
            save_path=fpath,
        )
        if not self.vid_rec.start():
            messagebox.showerror("Error", "Could not start screen capture.")
            self.app_state = "idle"
            self._set_btn_states()
            return

        if self.cfg["audio"]:
            self.aud_rec = AudioRecorder()
            self.aud_rec.start()

        self.app_state   = "recording"
        self.elapsed_sec = 0
        self._set_btn_states()
        self._start_timer()
        self.status_lbl.config(text="  Recording...", fg=START_CLR)
        self.rec_badge.place(x=8, y=8)
        self._blink()

    def _on_pause(self):
        if self.app_state == "recording":
            self.app_state = "paused"
            if self.vid_rec: self.vid_rec.pause()
            if self.aud_rec: self.aud_rec.pause()
            self.btn_pause.config(text="  RESUME  (F11)")
            self.status_lbl.config(text="  Paused", fg=PAUSE_CLR)
            self._stop_timer()
            self.rec_badge.place_forget()

        elif self.app_state == "paused":
            self.app_state = "recording"
            if self.vid_rec: self.vid_rec.resume()
            if self.aud_rec: self.aud_rec.resume()
            self.btn_pause.config(text="  PAUSE  (F11)")
            self.status_lbl.config(text="  Recording...", fg=START_CLR)
            self._start_timer()
            self._blink()

    def _on_stop(self):
        if self.app_state not in ("recording", "paused"):
            return
        self.app_state = "idle"
        self._stop_timer()
        self.rec_badge.place_forget()
        self.status_lbl.config(text="  Saving file...", fg=PAUSE_CLR)
        self._set_btn_states()
        threading.Thread(target=self._finalize, daemon=True).start()

    def _finalize(self):
        if self.vid_rec:
            self.vid_rec.stop()
        wav = None
        if self.aud_rec and self.cfg["audio"]:
            self.aud_rec.stop()
            wav = self.aud_rec.save_wav()
        if self.vid_rec:
            final = self.vid_rec.merge_and_save(wav)
            self.after(0, lambda: self._done(final))
        else:
            self.after(0, lambda: self._done(None))

    def _done(self, path):
        self.timer_lbl.config(text="00:00:00")
        self.btn_pause.config(text="  PAUSE  (F11)")
        if path:
            self.status_lbl.config(
                text=f"  Saved: {os.path.basename(path)}", fg=GREEN)
            messagebox.showinfo(
                "Recording Saved",
                f"Your recording has been saved to:\n\n{path}"
            )
        else:
            self.status_lbl.config(text="  Ready to Record", fg=GREEN)

    # ─── Clean close ───────────────────────────────────────────────────────────
    def on_close(self):
        if self.app_state in ("recording", "paused"):
            if not messagebox.askyesno(
                    "Quit", "Recording in progress. Stop and quit?"):
                return
            self._on_stop()
            time.sleep(0.5)
        if KEYBOARD_OK:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def main():
    app = SmartScreenRecorder()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
