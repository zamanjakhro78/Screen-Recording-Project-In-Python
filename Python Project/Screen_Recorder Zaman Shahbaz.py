import sys
import subprocess
import importlib

REQUIRED = {
    "opencv-python": "cv2",
    "numpy": "numpy",
    "pyautogui": "pyautogui",
    "pillow": "PIL",
    "keyboard": "keyboard",
}

def _install(pkg):
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
        return

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

_ensure_deps()

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

BG = "#1e1e2f"
PANEL = "#2a2a3d"
PANEL2 = "#23233a"
START_CLR = "#ff4d4d"
STOP_CLR = "#cc1a1a"
PAUSE_CLR = "#ffa500"
GREEN = "#4caf50"
WHITE = "#ffffff"
GREY = "#888899"
ACCENT = "#7b61ff"
BORDER = "#3a3a55"

class AudioRecorder:
    CHUNK = 1024
    CHAN = 1
    RATE = 44100

    def __init__(self):
        self.pa = None
        self.stream = None
        self.frames = []
        self._active = False
        self._paused = False
        self.tmpfile = None
        self.enabled = PYAUDIO_OK

    def start(self):
        if not self.enabled:
            return
        self.frames = []
        self._active = True
        self._paused = False
        try:
            self.pa = pyaudio.PyAudio()
            self.stream = self.pa.open(
                format=pyaudio.paInt16, channels=self.CHAN,
                rate=self.RATE, input=True,
                frames_per_buffer=self.CHUNK
            )
            threading.Thread(target=self._loop, daemon=True).start()
        except Exception as e:
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
                if hasattr(obj, "stop_stream"): obj.stop_stream()
                if hasattr(obj, "close"): obj.close()
                if hasattr(obj, "terminate"): obj.terminate()
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


class VideoRecorder:
    def __init__(self, fps=30, quality="High", save_path="", region=None):
        self.fps = fps
        self.quality = quality
        self.save_path = save_path
        self.region = region
        self._active = False
        self._paused = False
        self.out = None
        self.tmp_video = None
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


class SmartScreenRecorder(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Smart Screen Recorder")
        self.geometry("800x580")
        self.minsize(720, 530)
        self.configure(bg=BG)

        self.app_state = "idle"
        self.elapsed_sec = 0
        self._timer_job = None
        self.vid_rec = None
        self.aud_rec = AudioRecorder()

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
        self._refresh_dep_status()

    def _style_ttk(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TCombobox",
                    fieldbackground=PANEL2, background=PANEL2,
                    foreground=WHITE, selectbackground=ACCENT,
                    arrowcolor=WHITE, bordercolor=BORDER)

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

    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        self._build_left(body)
        self._build_right(body)

    def _build_left(self, parent):
        left = tk.Frame(parent, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=22, pady=18)

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

        bf = tk.Frame(left, bg=BG)
        bf.pack(fill="x", pady=(0, 10))

        self.btn_start = tk.Button(bf, text="START", command=self._on_start)
        self.btn_pause = tk.Button(bf, text="PAUSE", command=self._on_pause)
        self.btn_stop = tk.Button(bf, text="STOP", command=self._on_stop)

    def _build_right(self, parent):
        right = tk.Frame(parent, bg=PANEL, width=210)
        right.pack(side="right", fill="y")

    def _build_footer(self):
        f = tk.Frame(self, bg=PANEL2, pady=7)
        f.pack(fill="x", side="bottom")

    def _refresh_dep_status(self):
        pass

    def _bind_hotkeys(self):
        pass

    def _on_start(self):
        pass

    def _on_pause(self):
        pass

    def _on_stop(self):
        pass


def main():
    app = SmartScreenRecorder()
    app.mainloop()

if __name__ == "__main__":
    main()