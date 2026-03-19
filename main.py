"""
THUNDER_VOX — Real-Time Warhammer 40k Voice Modulator
Built for Loki & Ryan. Talk into your mic, sound like the God-Emperor.
"""

import json
import time
import wave
import threading
import datetime
import traceback
import platform
from pathlib import Path

import numpy as np
import sounddevice as sd
from pedalboard import (
    Pedalboard, PitchShift, Reverb, LowShelfFilter,
    HighShelfFilter, Distortion, Compressor, Gain, NoiseGate,
    Limiter, PeakFilter,
)
import customtkinter as ctk

# =====================================================================
# SETTINGS — you can change these numbers to tweak things
# =====================================================================
SAMPLE_RATE = 44100
BLOCK_SIZE = 1024       # Audio buffer size. Bigger = more stable, tiny bit more delay
PRESETS_FILE = Path(__file__).parent / "presets.json"
SOUNDS_DIR = Path(__file__).parent / "sounds"

# =====================================================================
# COLORS — the Warhammer 40k look
# =====================================================================
# Background layers (darkest to lightest)
C_VOID       = "#000000"   # Pure black background
C_PANEL      = "#0c0a08"   # Slightly warm dark panels
C_CARD       = "#14110e"   # Card/section background
C_CARD_HOVER = "#1e1a14"   # Hover state

# Gold tones (the imperial color)
C_GOLD       = "#c8a832"   # Primary gold — warm and rich
C_GOLD_BRIGHT= "#e8c840"   # Highlighted gold
C_GOLD_DIM   = "#6a5820"   # Subtle gold for borders
C_GOLD_GLOW  = "#ffd84a"   # Bright glow gold

# Parchment & text
C_PARCHMENT  = "#e8dcc4"   # Aged paper color — main readable text
C_PARCHMENT_DIM = "#a09078" # Dimmer parchment for descriptions
C_WHITE      = "#f4ede0"   # Brightest readable text

# Accents
C_CRIMSON    = "#8b1a1a"   # Blood red — subtle accents
C_RED_BRIGHT = "#d44"      # Warning/recording red
C_GREEN      = "#3a3"      # Success green
C_GREEN_DIM  = "#284"      # Dim green for borders

# Borders & frames
C_BORDER     = "#2a2418"   # Warm dark gold border
C_BORDER_GLOW= "#4a3c20"   # Active border glow

# Per-voice colors: (button_bg, hover, text_color)
VOICE_STYLE = {
    "EMPEROR_GOD":     ("#1a1608", "#2a2410", C_GOLD_GLOW),
    "SPACE_MARINE":    ("#0c1420", "#142030", "#68a8e8"),
    "CHAOS_LORD":      ("#1a0808", "#2a1010", "#e85050"),
    "INQUISITOR":      ("#141018", "#201828", "#b898d8"),
    "ORK_WAAAGH":      ("#0c1a08", "#1a2a10", "#70d850"),
    "PRIMARIS_CAPTAIN": ("#0c1420", "#142030", "#68a8e8"),
    "TECH_PRIEST":     ("#14101a", "#201828", "#a880d8"),
}

# =====================================================================
# FONT SETUP — finds the best fonts on your computer
# =====================================================================
_TITLE_FONT = "Impact"
_BODY_FONT = "Arial"

def _setup_fonts():
    """Detect installed fonts. Prefers gothic/serif for the 40k feel."""
    global _TITLE_FONT, _BODY_FONT
    try:
        import tkinter as tk, tkinter.font as tkfont
        r = tk.Tk(); r.withdraw()
        installed = {f.lower() for f in tkfont.families()}
        r.destroy()
        # Try loading the bundled gothic font (Windows only)
        ttf = Path(__file__).parent / "UnifrakturMaguntia-Regular.ttf"
        if ttf.exists() and platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.gdi32.AddFontResourceExW(str(ttf), 0x10, 0)
                r2 = tk.Tk(); r2.withdraw()
                installed = {f.lower() for f in tkfont.families()}
                r2.destroy()
            except Exception:
                pass
        for f in ["unifrakturmaguntia", "old english text mt", "impact"]:
            if f in installed: _TITLE_FONT = f.title(); break
        for f in ["segoe ui", "georgia", "arial"]:
            if f in installed: _BODY_FONT = f.title(); break
    except Exception:
        pass
    print(f"  Fonts: {_TITLE_FONT} / {_BODY_FONT}")

# Font size constants — everything big for Loki
F_HUGE  = 64    # Main title
F_BIG   = 32    # Preset names, big labels
F_MED   = 22    # Buttons, descriptions
F_NORM  = 18    # Body text, status
F_SMALL = 15    # Fine print only


# =====================================================================
# AUDIO ENGINE — the part that actually changes your voice
# =====================================================================
class VoiceEngine:
    """Takes mic input, runs it through effects, sends it to speakers."""

    def __init__(self):
        self.board = None          # The effects chain
        self.stream = None         # The audio stream
        self.is_active = False     # Is it currently processing?
        self.needs_heal = False    # Did something break?
        self.preset_name = None    # Which voice is active?
        self.input_device = None   # Which mic?
        self.output_device = None  # Which speakers?
        self.errors = []
        self.voice_detected = False
        self.latency_ms = 0.0
        self._vc = 0; self._sc = 0; self._last_st = 0.0

        # Recording state
        self.is_recording = False
        self.rec_frames = []
        self.rec_lock = threading.Lock()

        # Load the voice presets from presets.json
        self.presets = self._load_presets()
        first_key = list(self.presets.keys())[0]
        self.build_effects(first_key)

    def _load_presets(self):
        try:
            with open(PRESETS_FILE) as f:
                return json.load(f)
        except Exception:
            return {"EMPEROR_GOD": {
                "display_name": "EMPEROR", "description": "Fallback",
                "pitch_shift_semitones": -8.0, "low_shelf_gain_db": 10.0,
                "low_shelf_cutoff_hz": 200.0, "high_shelf_gain_db": -1.0,
                "high_shelf_cutoff_hz": 5000.0, "reverb_room_size": 0.55,
                "reverb_wet_level": 0.15, "reverb_damping": 0.6,
                "distortion_drive_db": 0.0, "compressor_threshold_db": -16.0,
                "compressor_ratio": 3.0, "gain_db": 5.0,
            }}

    def build_effects(self, preset_key):
        """Build the voice effect chain from a preset.

        Chain order matters for natural sound:
        1. Pitch FIRST (cleanest input = cleanest shift)
        2. EQ to shape the tone
        3. Light distortion only if preset wants it
        4. Gentle reverb for space
        5. Limiter at the end to prevent clipping
        NO compressor — that's what causes the robotic squash.
        NO noise gate — it chops the start of words.
        """
        p = self.presets[preset_key]
        self.preset_name = preset_key

        chain = []

        # 1. Pitch shift — always first, on clean audio
        if p["pitch_shift_semitones"] != 0.0:
            chain.append(PitchShift(semitones=p["pitch_shift_semitones"]))

        # 2. EQ shaping — bass and treble
        if p["low_shelf_gain_db"] != 0.0:
            chain.append(LowShelfFilter(
                cutoff_frequency_hz=p["low_shelf_cutoff_hz"],
                gain_db=p["low_shelf_gain_db"]))
        if p["high_shelf_gain_db"] != 0.0:
            chain.append(HighShelfFilter(
                cutoff_frequency_hz=p["high_shelf_cutoff_hz"],
                gain_db=p["high_shelf_gain_db"]))

        # 3. Distortion — only if preset actually wants it (skip at 0)
        if p["distortion_drive_db"] > 0.5:
            chain.append(Distortion(drive_db=p["distortion_drive_db"]))

        # 4. Volume
        if p["gain_db"] != 0.0:
            chain.append(Gain(gain_db=p["gain_db"]))

        # 5. Reverb — only if preset wants echo
        if p["reverb_wet_level"] > 0.01:
            chain.append(Reverb(
                room_size=p["reverb_room_size"],
                wet_level=p["reverb_wet_level"],
                damping=p["reverb_damping"]))

        # 6. Safety limiter — prevents clipping, very gentle
        chain.append(Limiter(threshold_db=-3.0, release_ms=120.0))

        self.board = Pedalboard(chain)

    def find_devices(self):
        """Find all microphones and speakers on this computer."""
        inputs, outputs = [], []
        try:
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0:
                    inputs.append((i, d["name"]))
                if d["max_output_channels"] > 0:
                    outputs.append((i, d["name"]))
        except Exception as e:
            self._err(f"Device scan failed: {e}")
        return inputs, outputs

    def auto_pick_devices(self, inputs, outputs):
        """Automatically pick the best mic and speakers (prefers HyperX)."""
        skip = {"ngenuity", "system use", "sound mapper", "digital output"}

        for idx, name in inputs:
            nl = name.lower()
            if any(s in nl for s in skip): continue
            if "hyperx" in nl:
                self.input_device = idx; break
        if self.input_device is None:
            for idx, name in inputs:
                if not any(s in name.lower() for s in skip):
                    self.input_device = idx; break

        for idx, name in outputs:
            nl = name.lower()
            if any(s in nl for s in skip): continue
            if ("hyperx" in nl or "speaker" in nl or "headphone" in nl):
                self.output_device = idx; break
        if self.output_device is None:
            for idx, name in outputs:
                if not any(s in name.lower() for s in skip):
                    self.output_device = idx; break

        # Print what we picked
        for idx, name in inputs:
            if idx == self.input_device: print(f"  Mic:     {name}")
        for idx, name in outputs:
            if idx == self.output_device: print(f"  Speaker: {name}")

    def _audio_callback(self, indata, outdata, frames, time_info, status):
        """This runs ~43 times per second. Must be FAST — no file I/O, no prints."""
        try:
            if status:
                now = time.perf_counter()
                if now - self._last_st > 10.0:
                    self._last_st = now
                    self._err(f"Audio: {status}")

            audio = indata[:, 0].copy()
            rms = float(np.sqrt(np.mean(audio ** 2)))

            # Auto-gain: boost quiet input to target level for consistent stream volume
            if rms > 0.005 and rms < 0.06:
                boost = min(0.06 / rms, 4.0)  # Max 4x boost (~12dB)
                audio *= boost
                np.clip(audio, -1.0, 1.0, out=audio)

            # Track if someone is talking
            if rms > 0.008:
                self._vc += 1; self._sc = 0
                if self._vc > 4: self.voice_detected = True
            else:
                self._sc += 1; self._vc = 0
                if self._sc > 25: self.voice_detected = False

            # Run voice through effects
            t0 = time.perf_counter()
            result = self.board(audio.reshape(1, -1), SAMPLE_RATE)[0]
            np.clip(result, -1.0, 1.0, out=result)
            outdata[:, 0] = result

            # Measure how fast this is running
            self.latency_ms = (BLOCK_SIZE/SAMPLE_RATE)*2000 + (time.perf_counter()-t0)*1000

            # Save to recording buffer if recording
            if self.is_recording:
                with self.rec_lock:
                    self.rec_frames.append(result.copy())
        except Exception:
            outdata.fill(0)
            self.needs_heal = True

    def start(self):
        """Start the voice processing."""
        if self.is_active: return True
        try:
            kw = {"samplerate": SAMPLE_RATE, "blocksize": BLOCK_SIZE,
                  "channels": 1, "dtype": "float32", "callback": self._audio_callback}
            if self.input_device is not None and self.output_device is not None:
                kw["device"] = (self.input_device, self.output_device)
            self.stream = sd.Stream(**kw)
            self.stream.start()
            self.is_active = True
            self.needs_heal = False
            return True
        except Exception as e:
            self._err(f"Start failed: {e}")
            return False

    def stop(self):
        """Stop voice processing."""
        try:
            if self.stream:
                self.stream.stop(); self.stream.close(); self.stream = None
            self.is_active = False
        except Exception: pass

    def heal(self):
        """Fix audio if something broke."""
        self.stop(); time.sleep(0.3); return self.start()

    def test_my_voice(self, duration=3.0):
        """Record your voice, run it through effects, play it back so you can hear it."""
        try:
            idev = self.input_device if self.input_device is not None else sd.default.device[0]
            odev = self.output_device if self.output_device is not None else sd.default.device[1]
            rec = sd.rec(int(SAMPLE_RATE * duration), samplerate=SAMPLE_RATE,
                         channels=1, dtype="float32", device=idev)
            sd.wait()
            audio = rec[:, 0]
            if np.max(np.abs(audio)) < 0.003:
                return False, "I didn't hear anything — try speaking louder!"
            out = self.board(audio.reshape(1, -1), SAMPLE_RATE)[0]
            np.clip(out, -1, 1, out=out)
            sd.play(out, samplerate=SAMPLE_RATE, device=odev)
            sd.wait()
            return True, "Did you hear that? That's your god-voice!"
        except Exception as e:
            return False, f"Something went wrong: {e}"

    def play_soundclip(self, filepath):
        """Play an MP3/WAV file through the current voice effects."""
        try:
            from pedalboard.io import AudioFile
            with AudioFile(filepath) as f:
                audio = f.read(f.frames)
                sr = f.samplerate
            if audio.shape[0] > 1:
                audio = np.mean(audio, axis=0, keepdims=True)
            if sr != SAMPLE_RATE:
                from scipy.signal import resample
                n = int(audio.shape[1] * SAMPLE_RATE / sr)
                audio = resample(audio[0], n).reshape(1, -1).astype(np.float32)
            out = self.board(audio, SAMPLE_RATE)[0]
            np.clip(out, -1, 1, out=out)
            dev = self.output_device if self.output_device is not None else sd.default.device[1]
            sd.play(out, samplerate=SAMPLE_RATE, device=dev); sd.wait()
            return True
        except Exception as e:
            self._err(f"Clip: {e}"); return False

    def start_recording(self):
        with self.rec_lock: self.rec_frames = []
        self.is_recording = True

    def stop_recording(self):
        self.is_recording = False
        with self.rec_lock:
            if not self.rec_frames: return None
            audio = np.concatenate(self.rec_frames); self.rec_frames = []
        path = Path(__file__).parent / f"rec_{self.preset_name}_{datetime.datetime.now():%Y%m%d_%H%M%S}.wav"
        try:
            d = (audio * 32767).astype(np.int16)
            with wave.open(str(path), "w") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE)
                w.writeframes(d.tobytes())
            return str(path)
        except Exception: return None

    def _err(self, msg):
        self.errors.append(f"[{datetime.datetime.now():%H:%M:%S}] {msg}")
        if len(self.errors) > 50: self.errors = self.errors[-25:]


# =====================================================================
# THE APP — what you see on screen
# =====================================================================
class ThunderVoxApp(ctk.CTk):

    # UI modes
    MODE_FULL = "full"        # Full window — all controls, sliders, soundboard
    MODE_COMPACT = "compact"  # Narrow sidebar — just presets + essential controls
    MODE_MINI = "mini"        # Tiny floating strip — active voice + test button

    def __init__(self):
        super().__init__()

        self.title("THUNDER_VOX")
        self.configure(fg_color=C_VOID)

        # State
        self.engine = VoiceEngine()
        self.recording = False
        self.active_key = None
        self.cycling = False
        self._cycle_timer = None
        self._ui_mode = self.MODE_FULL
        self._dock_side = None  # None=float, "left", "right"
        self._sliders = {}
        self._egg_revealed = False
        self._pulse_state = False

        # Devices
        self.inputs, self.outputs = self.engine.find_devices()
        self.engine.auto_pick_devices(self.inputs, self.outputs)

        # Build initial UI
        self._apply_mode(self.MODE_FULL)

        if self.inputs and self.outputs:
            self.after(500, self._start_audio)

        self._monitor()
        self.protocol("WM_DELETE_WINDOW", self._quit)

    def _apply_mode(self, mode, dock=None):
        """Switch UI mode. Rebuilds the entire interface."""
        self._ui_mode = mode
        self._dock_side = dock

        # Destroy existing UI
        for w in self.winfo_children():
            w.destroy()

        # Get screen dimensions
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        if mode == self.MODE_FULL:
            self.overrideredirect(False)
            self.geometry("1100x1000")
            self.minsize(900, 750)
            self.attributes("-topmost", False)
            self._build_ui()

        elif mode == self.MODE_COMPACT:
            w = 340
            self.overrideredirect(False)
            self.minsize(300, 400)
            self.attributes("-topmost", True)
            if dock == "left":
                self.geometry(f"{w}x{screen_h}+0+0")
            elif dock == "right":
                self.geometry(f"{w}x{screen_h}+{screen_w - w}+0")
            else:
                self.geometry(f"{w}x800")
            self._build_compact_ui()

        elif mode == self.MODE_MINI:
            h = 70
            self.overrideredirect(True)
            self.attributes("-topmost", True)
            if dock == "left":
                self.geometry(f"400x{screen_h}+0+0")
                self._build_mini_vertical()
            elif dock == "right":
                self.geometry(f"400x{screen_h}+{screen_w - 400}+0")
                self._build_mini_vertical()
            else:
                self.geometry(f"800x{h}+{(screen_w-800)//2}+0")
                self._build_mini_ui()

    # =================================================================
    # BUILD THE INTERFACE
    # =================================================================
    def _build_ui(self):
        # Scrollable main area
        self.main = ctk.CTkScrollableFrame(self, fg_color=C_VOID,
            scrollbar_button_color=C_GOLD_DIM,
            scrollbar_button_hover_color=C_GOLD)
        self.main.pack(fill="both", expand=True)

        # ── HEADER — Stream-worthy Imperial banner ──────────
        hdr_outer = ctk.CTkFrame(self.main, fg_color="#1a1408", corner_radius=0,
            border_width=0)
        hdr_outer.pack(fill="x")

        # Top gold accent bar (thick)
        ctk.CTkFrame(hdr_outer, fg_color=C_GOLD, height=5, corner_radius=0).pack(fill="x")

        # Crimson accent line
        ctk.CTkFrame(hdr_outer, fg_color=C_CRIMSON, height=2, corner_radius=0).pack(fill="x")

        hdr = ctk.CTkFrame(hdr_outer, fg_color=C_PANEL, corner_radius=0)
        hdr.pack(fill="x")

        pad = ctk.CTkFrame(hdr, fg_color="transparent")
        pad.pack(fill="x", padx=28, pady=(18, 4))

        # Aquila line above title
        ctk.CTkLabel(pad,
            text="\u2726 \u2694 \u269C  ===///|\\\\\\===  \u269C \u2694 \u2726",
            font=ctk.CTkFont(family="Courier New", size=16),
            text_color=C_GOLD_DIM).pack(anchor="center", pady=(0, 6))

        ctk.CTkLabel(pad, text="THUNDER_VOX",
            font=ctk.CTkFont(family=_TITLE_FONT, size=F_HUGE, weight="bold"),
            text_color=C_GOLD_BRIGHT).pack(anchor="center")

        ctk.CTkLabel(pad, text="\u2620  VOICE OF THE GOD-EMPEROR  \u2620",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_MED, weight="bold"),
            text_color=C_CRIMSON).pack(anchor="center")

        # Divider with skulls
        ctk.CTkLabel(pad,
            text="\u2726 \u25C6 \u2726 \u25C6 \u2726",
            font=ctk.CTkFont(size=14),
            text_color=C_GOLD_DIM).pack(anchor="center", pady=(6, 0))

        ctk.CTkFrame(hdr, fg_color=C_GOLD_DIM, height=1, corner_radius=0).pack(fill="x", pady=(8, 0))

        # Welcome / status
        status_pad = ctk.CTkFrame(hdr, fg_color="transparent")
        status_pad.pack(fill="x", padx=28, pady=(8, 14))

        self.status = ctk.CTkLabel(status_pad,
            text="Welcome! Pick a voice below, then hit TEST MY VOICE to hear yourself.",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM),
            text_color=C_PARCHMENT, wraplength=900, justify="left")
        self.status.pack(anchor="w")

        # Bottom border of header
        ctk.CTkFrame(hdr_outer, fg_color=C_CRIMSON, height=1, corner_radius=0).pack(fill="x")
        ctk.CTkFrame(hdr_outer, fg_color=C_GOLD_DIM, height=2, corner_radius=0).pack(fill="x")

        # ── VOICE INDICATOR ─────────────────────────────────
        self.ind_frame = ctk.CTkFrame(self.main, fg_color=C_CARD, corner_radius=0,
            border_width=0)
        self.ind_frame.pack(fill="x", pady=(2, 0))

        ind_pad = ctk.CTkFrame(self.ind_frame, fg_color="transparent")
        ind_pad.pack(fill="x", padx=28, pady=14)

        self.voice_name = ctk.CTkLabel(ind_pad, text="No voice selected yet",
            font=ctk.CTkFont(family=_TITLE_FONT, size=48, weight="bold"),
            text_color=C_PARCHMENT_DIM)
        self.voice_name.pack(anchor="w")

        self.voice_desc = ctk.CTkLabel(ind_pad, text="Pick one below to get started!",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM),
            text_color=C_PARCHMENT_DIM)
        self.voice_desc.pack(anchor="w")

        # Info row: latency + voice detection
        info = ctk.CTkFrame(ind_pad, fg_color="transparent")
        info.pack(anchor="w", pady=(6, 0))
        self.latency_lbl = ctk.CTkLabel(info, text="",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_SMALL), text_color=C_PARCHMENT_DIM)
        self.latency_lbl.pack(side="left", padx=(0, 20))
        self.voice_lbl = ctk.CTkLabel(info, text="",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_SMALL, weight="bold"),
            text_color=C_PARCHMENT_DIM)
        self.voice_lbl.pack(side="left")

        # Gold bar under indicator (changes color per voice)
        self.ind_bar = ctk.CTkFrame(self.main, fg_color=C_BORDER, height=3, corner_radius=0)
        self.ind_bar.pack(fill="x")

        # ── VOICE PRESETS ───────────────────────────────────
        ctk.CTkLabel(self.main, text="PICK YOUR VOICE",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM, weight="bold"),
            text_color=C_GOLD_DIM).pack(anchor="w", padx=28, pady=(14, 6))

        grid = ctk.CTkFrame(self.main, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=24)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self.voice_btns = {}
        self.voice_cards = {}
        for i, (key, p) in enumerate(self.engine.presets.items()):
            row, col = i // 2, i % 2
            style = VOICE_STYLE.get(key, (C_CARD, C_CARD_HOVER, C_GOLD))
            bg, hov, txt = style
            hk = f"  [F{i+1}]" if i < 7 else ""

            card = ctk.CTkFrame(grid, fg_color=bg, corner_radius=10,
                border_width=2, border_color=C_BORDER)
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            btn = ctk.CTkButton(card,
                text=f"{p['display_name']}{hk}",
                font=ctk.CTkFont(family=_TITLE_FONT, size=F_BIG, weight="bold"),
                height=110, fg_color="transparent", hover_color=hov,
                text_color=txt, corner_radius=8,
                command=lambda k=key: self._pick_voice(k))
            btn.pack(fill="both", expand=True, padx=3, pady=(3, 0))

            ctk.CTkLabel(card, text=p["description"],
                font=ctk.CTkFont(family=_BODY_FONT, size=F_SMALL),
                text_color=C_PARCHMENT_DIM, wraplength=420,
            ).pack(padx=12, pady=(2, 10), anchor="w")

            self.voice_btns[key] = btn
            self.voice_cards[key] = card
            if i < 7:
                self.bind(f"<F{i+1}>", lambda e, k=key: self._pick_voice(k))

        for r in range((len(self.engine.presets) + 1) // 2):
            grid.rowconfigure(r, weight=1)

        # ── VOICE TUNING SLIDERS ───────────────────────────
        ctk.CTkFrame(self.main, fg_color=C_BORDER, height=1, corner_radius=0
            ).pack(fill="x", padx=24, pady=(12, 0))

        ctk.CTkLabel(self.main, text="TUNE YOUR VOICE — drag sliders to adjust live",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM, weight="bold"),
            text_color=C_GOLD_DIM).pack(anchor="w", padx=28, pady=(10, 4))

        sliders_frame = ctk.CTkFrame(self.main, fg_color=C_CARD, corner_radius=10,
            border_width=1, border_color=C_BORDER)
        sliders_frame.pack(fill="x", padx=24, pady=(0, 8))

        # Slider config: (label, param_key, min, max, default)
        self._slider_defs = [
            ("PITCH",      "pitch_shift_semitones", -12.0, 8.0),
            ("BASS BOOST",  "low_shelf_gain_db",    -10.0, 14.0),
            ("TREBLE",      "high_shelf_gain_db",   -8.0,  8.0),
            ("DISTORTION",  "distortion_drive_db",   0.0,  18.0),
            ("REVERB",      "reverb_wet_level",      0.0,  0.5),
            ("ECHO SIZE",   "reverb_room_size",      0.05, 0.95),
            ("VOLUME",      "gain_db",               0.0,  10.0),
        ]
        self._sliders = {}

        for label, param, lo, hi in self._slider_defs:
            row = ctk.CTkFrame(sliders_frame, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(6, 2))

            ctk.CTkLabel(row, text=label, width=120,
                font=ctk.CTkFont(family=_BODY_FONT, size=F_SMALL, weight="bold"),
                text_color=C_GOLD, anchor="w").pack(side="left")

            val_label = ctk.CTkLabel(row, text="0.0", width=60,
                font=ctk.CTkFont(family=_BODY_FONT, size=F_SMALL),
                text_color=C_PARCHMENT_DIM, anchor="e")
            val_label.pack(side="right", padx=(8, 0))

            slider = ctk.CTkSlider(row,
                from_=lo, to=hi,
                height=28, width=400,
                fg_color=C_BORDER, progress_color=C_GOLD_DIM,
                button_color=C_GOLD, button_hover_color=C_GOLD_BRIGHT,
                command=lambda v, p=param, vl=val_label: self._on_slider(p, v, vl))
            slider.pack(side="left", fill="x", expand=True, padx=(8, 8))

            self._sliders[param] = (slider, val_label)

        # Save button
        save_row = ctk.CTkFrame(sliders_frame, fg_color="transparent")
        save_row.pack(fill="x", padx=16, pady=(4, 10))

        ctk.CTkButton(save_row, text="SAVE TO PRESET",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_SMALL, weight="bold"),
            height=40, fg_color=C_GOLD_DIM, hover_color=C_GOLD,
            text_color=C_VOID, corner_radius=6,
            command=self._save_preset).pack(side="left", padx=(0, 8))

        ctk.CTkButton(save_row, text="RESET",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_SMALL, weight="bold"),
            height=40, fg_color=C_BORDER, hover_color=C_CARD_HOVER,
            text_color=C_PARCHMENT_DIM, corner_radius=6,
            command=self._reset_sliders).pack(side="left")

        # ── MAIN BUTTONS ────────────────────────────────────
        ctk.CTkFrame(self.main, fg_color=C_BORDER, height=1, corner_radius=0
            ).pack(fill="x", padx=24, pady=(4, 0))

        cmds = ctk.CTkFrame(self.main, fg_color="transparent")
        cmds.pack(fill="x", padx=24, pady=(8, 0))

        # TEST MY VOICE — the hero button
        self.test_btn = ctk.CTkButton(cmds,
            text="TEST MY VOICE — speak for 3 seconds and hear yourself!",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_MED, weight="bold"),
            height=90, fg_color="#2a1a00", hover_color="#4a3000",
            text_color=C_GOLD_GLOW, corner_radius=10,
            border_width=2, border_color=C_GOLD_DIM,
            command=self._test_voice)
        self.test_btn.pack(fill="x", pady=(0, 5))

        # AUTO-CYCLE
        self.cycle_btn = ctk.CTkButton(cmds,
            text="AUTO-CYCLE ALL VOICES (10s each) — hit STOP when you like one",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM, weight="bold"),
            height=70, fg_color="#140a20", hover_color="#201430",
            text_color="#b898d8", corner_radius=8,
            border_width=2, border_color="#4a3060",
            command=self._toggle_cycle)
        self.cycle_btn.pack(fill="x", pady=(0, 5))

        # Utility row: Record, Heal
        utils = ctk.CTkFrame(cmds, fg_color="transparent")
        utils.pack(fill="x", pady=(0, 5))

        self.rec_btn = ctk.CTkButton(utils, text="RECORD [F8]",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM, weight="bold"),
            height=60, fg_color=C_CRIMSON, hover_color=C_RED_BRIGHT,
            text_color=C_WHITE, corner_radius=8,
            command=self._toggle_rec)
        self.rec_btn.pack(side="left", padx=(0, 4), expand=True, fill="x")

        ctk.CTkButton(utils, text="HEAL AUDIO [F9]",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM, weight="bold"),
            height=60, fg_color=C_GREEN_DIM, hover_color=C_GREEN,
            text_color=C_WHITE, corner_radius=8,
            command=self._heal
        ).pack(side="left", padx=(4, 0), expand=True, fill="x")

        # STREAM MODE — sends god-voice to Discord/OBS via HyperX virtual device
        self.stream_mode = False
        self.stream_btn = ctk.CTkButton(cmds,
            text="STREAM MODE: OFF — click to send god-voice to Discord/OBS",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM, weight="bold"),
            height=60, fg_color="#0a1420", hover_color="#142030",
            text_color="#6090c0", corner_radius=8,
            border_width=2, border_color="#203050",
            command=self._toggle_stream_mode)
        self.stream_btn.pack(fill="x", pady=(5, 0))

        # ── SOUNDBOARD ──────────────────────────────────────
        clips = []
        if SOUNDS_DIR.exists():
            for ext in ("*.mp3", "*.wav", "*.ogg"):
                clips.extend(SOUNDS_DIR.glob(ext))

        if clips:
            ctk.CTkFrame(self.main, fg_color=C_BORDER, height=1, corner_radius=0
                ).pack(fill="x", padx=24, pady=(8, 0))

            ctk.CTkLabel(self.main, text="SOUNDBOARD — plays through your current voice",
                font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM, weight="bold"),
                text_color=C_GOLD_DIM).pack(anchor="w", padx=28, pady=(8, 4))

            sb = ctk.CTkFrame(self.main, fg_color="transparent")
            sb.pack(fill="x", padx=24)

            for clip in clips:
                name = clip.stem.replace("-", " ").replace("_", " ").upper()
                ctk.CTkButton(sb, text=name,
                    font=ctk.CTkFont(family=_TITLE_FONT, size=F_MED, weight="bold"),
                    height=70, fg_color="#1a1200", hover_color="#2a2008",
                    text_color=C_GOLD, corner_radius=8,
                    border_width=2, border_color=C_GOLD_DIM,
                    command=lambda p=str(clip): self._play_clip(p),
                ).pack(fill="x", pady=3)

        # Hotkeys
        self.bind("<F8>", lambda e: self._toggle_rec())
        self.bind("<F9>", lambda e: self._heal())
        self.bind("<F12>", lambda e: self._test_voice())

        # ── MODE SWITCHER ──────────────────────────────────
        ctk.CTkFrame(self.main, fg_color=C_BORDER, height=1, corner_radius=0
            ).pack(fill="x", padx=24, pady=(10, 0))

        ctk.CTkLabel(self.main, text="WINDOW MODE",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_SMALL, weight="bold"),
            text_color=C_GOLD_DIM).pack(anchor="w", padx=28, pady=(8, 4))

        mode_frame = ctk.CTkFrame(self.main, fg_color="transparent")
        mode_frame.pack(fill="x", padx=24, pady=(0, 4))

        for text, mode, dock in [
            ("FULL",          self.MODE_FULL,    None),
            ("COMPACT",       self.MODE_COMPACT, None),
            ("DOCK LEFT",     self.MODE_COMPACT, "left"),
            ("DOCK RIGHT",    self.MODE_COMPACT, "right"),
            ("MINI BAR",      self.MODE_MINI,    None),
        ]:
            ctk.CTkButton(mode_frame, text=text,
                font=ctk.CTkFont(family=_BODY_FONT, size=12, weight="bold"),
                height=36, fg_color=C_BORDER, hover_color=C_CARD_HOVER,
                text_color=C_PARCHMENT_DIM, corner_radius=6, width=100,
                command=lambda m=mode, d=dock: self._apply_mode(m, d),
            ).pack(side="left", padx=2)

        # ── FOOTER — Claude Code easter egg ───────────────
        footer_outer = ctk.CTkFrame(self.main, fg_color="#0a0808", corner_radius=0)
        footer_outer.pack(fill="x", pady=(12, 0))

        ctk.CTkFrame(footer_outer, fg_color=C_GOLD_DIM, height=1, corner_radius=0).pack(fill="x")
        ctk.CTkFrame(footer_outer, fg_color=C_CRIMSON, height=1, corner_radius=0).pack(fill="x")

        footer = ctk.CTkFrame(footer_outer, fg_color="transparent")
        footer.pack(fill="x", padx=28, pady=12)

        # Easter egg — click to reveal
        self._egg_revealed = False
        self._egg_label = ctk.CTkLabel(footer,
            text="\u269C  For the Emperor  \u269C",
            font=ctk.CTkFont(family=_BODY_FONT, size=13),
            text_color=C_GOLD_DIM, cursor="hand2")
        self._egg_label.pack(anchor="center")
        self._egg_label.bind("<Button-1>", self._easter_egg)

        # Build info line
        ctk.CTkLabel(footer,
            text="THUNDER_VOX v1.0  \u2022  Built by Loki  \u2022  Mentored by KHET-1",
            font=ctk.CTkFont(family=_BODY_FONT, size=11),
            text_color="#3a3428").pack(anchor="center", pady=(4, 0))

        ctk.CTkFrame(footer_outer, fg_color=C_CRIMSON, height=1, corner_radius=0).pack(fill="x")
        ctk.CTkFrame(footer_outer, fg_color=C_GOLD, height=4, corner_radius=0).pack(fill="x")

    # =================================================================
    # COMPACT MODE — narrow sidebar with just the essentials
    # =================================================================
    def _build_compact_ui(self):
        self.main = ctk.CTkScrollableFrame(self, fg_color=C_VOID,
            scrollbar_button_color=C_GOLD_DIM, scrollbar_button_hover_color=C_GOLD)
        self.main.pack(fill="both", expand=True)

        # Header
        ctk.CTkFrame(self.main, fg_color=C_GOLD, height=3, corner_radius=0).pack(fill="x")
        ctk.CTkLabel(self.main, text="THUNDER_VOX",
            font=ctk.CTkFont(family=_TITLE_FONT, size=28, weight="bold"),
            text_color=C_GOLD_BRIGHT).pack(pady=(10, 2))

        # Status
        self.status = ctk.CTkLabel(self.main, text="Ready",
            font=ctk.CTkFont(family=_BODY_FONT, size=12),
            text_color=C_PARCHMENT_DIM, wraplength=300)
        self.status.pack(pady=(0, 6))

        # Active voice indicator
        self.voice_name = ctk.CTkLabel(self.main, text="—",
            font=ctk.CTkFont(family=_TITLE_FONT, size=24, weight="bold"),
            text_color=C_GOLD_DIM)
        self.voice_name.pack(pady=(4, 2))
        self.voice_desc = ctk.CTkLabel(self.main, text="",
            font=ctk.CTkFont(family=_BODY_FONT, size=11), text_color=C_PARCHMENT_DIM)
        self.voice_desc.pack()
        self.ind_bar = ctk.CTkFrame(self.main, fg_color=C_BORDER, height=2, corner_radius=0)
        self.ind_bar.pack(fill="x", pady=(6, 6))

        # Latency / voice
        info = ctk.CTkFrame(self.main, fg_color="transparent")
        info.pack(fill="x", padx=8)
        self.latency_lbl = ctk.CTkLabel(info, text="",
            font=ctk.CTkFont(family=_BODY_FONT, size=11), text_color=C_PARCHMENT_DIM)
        self.latency_lbl.pack(side="left")
        self.voice_lbl = ctk.CTkLabel(info, text="",
            font=ctk.CTkFont(family=_BODY_FONT, size=11, weight="bold"), text_color=C_PARCHMENT_DIM)
        self.voice_lbl.pack(side="right")

        # Preset buttons — stacked vertically
        self.voice_btns = {}
        self.voice_cards = {}
        for i, (key, p) in enumerate(self.engine.presets.items()):
            style = VOICE_STYLE.get(key, (C_CARD, C_CARD_HOVER, C_GOLD))
            btn = ctk.CTkButton(self.main,
                text=p["display_name"],
                font=ctk.CTkFont(family=_TITLE_FONT, size=18, weight="bold"),
                height=50, fg_color=style[0], hover_color=style[1],
                text_color=style[2], corner_radius=6,
                command=lambda k=key: self._pick_voice(k))
            btn.pack(fill="x", padx=8, pady=2)
            self.voice_btns[key] = btn
            self.voice_cards[key] = btn  # In compact mode, btn IS the card
            if i < 7:
                self.bind(f"<F{i+1}>", lambda e, k=key: self._pick_voice(k))

        # Essential controls
        ctk.CTkFrame(self.main, fg_color=C_BORDER, height=1, corner_radius=0
            ).pack(fill="x", padx=8, pady=(8, 4))

        self.test_btn = ctk.CTkButton(self.main, text="TEST MY VOICE",
            font=ctk.CTkFont(family=_BODY_FONT, size=14, weight="bold"),
            height=50, fg_color="#2a1a00", hover_color="#4a3000",
            text_color=C_GOLD_GLOW, corner_radius=6,
            command=self._test_voice)
        self.test_btn.pack(fill="x", padx=8, pady=2)

        self.rec_btn = ctk.CTkButton(self.main, text="RECORD [F8]",
            font=ctk.CTkFont(family=_BODY_FONT, size=12, weight="bold"),
            height=40, fg_color=C_CRIMSON, hover_color=C_RED_BRIGHT,
            text_color=C_WHITE, corner_radius=6,
            command=self._toggle_rec)
        self.rec_btn.pack(fill="x", padx=8, pady=2)

        self.stream_mode = getattr(self, 'stream_mode', False)
        self.stream_btn = ctk.CTkButton(self.main, text="STREAM MODE",
            font=ctk.CTkFont(family=_BODY_FONT, size=12, weight="bold"),
            height=40, fg_color="#0a1420", hover_color="#142030",
            text_color="#6090c0", corner_radius=6,
            command=self._toggle_stream_mode)
        self.stream_btn.pack(fill="x", padx=8, pady=2)

        # Mode buttons at bottom
        ctk.CTkFrame(self.main, fg_color=C_BORDER, height=1, corner_radius=0
            ).pack(fill="x", padx=8, pady=(8, 4))

        modes = ctk.CTkFrame(self.main, fg_color="transparent")
        modes.pack(fill="x", padx=8, pady=4)
        for text, mode, dock in [("FULL", self.MODE_FULL, None),
                                  ("DOCK L", self.MODE_COMPACT, "left"),
                                  ("DOCK R", self.MODE_COMPACT, "right"),
                                  ("MINI", self.MODE_MINI, None)]:
            ctk.CTkButton(modes, text=text,
                font=ctk.CTkFont(family=_BODY_FONT, size=10, weight="bold"),
                height=30, fg_color=C_BORDER, hover_color=C_CARD_HOVER,
                text_color=C_PARCHMENT_DIM, corner_radius=4, width=70,
                command=lambda m=mode, d=dock: self._apply_mode(m, d),
            ).pack(side="left", padx=1, expand=True, fill="x")

        self.bind("<F8>", lambda e: self._toggle_rec())
        self.bind("<F9>", lambda e: self._heal())
        self.bind("<F12>", lambda e: self._test_voice())
        self.bind("<Escape>", lambda e: self._apply_mode(self.MODE_FULL))

    # =================================================================
    # MINI MODE — tiny floating bar
    # =================================================================
    def _build_mini_ui(self):
        """Horizontal mini bar — sits at top of screen."""
        bar = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0,
            border_width=0)
        bar.pack(fill="both", expand=True)

        # Make it draggable
        bar.bind("<Button-1>", self._drag_start)
        bar.bind("<B1-Motion>", self._drag_move)

        ctk.CTkFrame(bar, fg_color=C_GOLD, height=2, corner_radius=0).pack(fill="x")

        row = ctk.CTkFrame(bar, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(row, text="\u2620 THUNDER_VOX",
            font=ctk.CTkFont(family=_TITLE_FONT, size=18, weight="bold"),
            text_color=C_GOLD_BRIGHT).pack(side="left", padx=(4, 12))

        self.voice_name = ctk.CTkLabel(row, text="—",
            font=ctk.CTkFont(family=_TITLE_FONT, size=18, weight="bold"),
            text_color=C_GOLD_DIM)
        self.voice_name.pack(side="left", padx=(0, 12))

        self.voice_desc = ctk.CTkLabel(row, text="", text_color=C_VOID)  # Hidden in mini
        self.ind_bar = ctk.CTkFrame(row, fg_color=C_BORDER, width=3, height=30, corner_radius=0)
        self.ind_bar.pack(side="left", padx=4)

        # Status & monitoring labels (hidden but needed by _monitor)
        self.status = ctk.CTkLabel(row, text="", text_color=C_VOID)
        self.latency_lbl = ctk.CTkLabel(row, text="",
            font=ctk.CTkFont(family=_BODY_FONT, size=11), text_color=C_PARCHMENT_DIM)
        self.latency_lbl.pack(side="left", padx=4)
        self.voice_lbl = ctk.CTkLabel(row, text="",
            font=ctk.CTkFont(family=_BODY_FONT, size=11, weight="bold"), text_color=C_PARCHMENT_DIM)
        self.voice_lbl.pack(side="left", padx=4)

        # Preset quick buttons
        self.voice_btns = {}
        self.voice_cards = {}
        for i, (key, p) in enumerate(self.engine.presets.items()):
            style = VOICE_STYLE.get(key, (C_CARD, C_CARD_HOVER, C_GOLD))
            btn = ctk.CTkButton(row, text=p["display_name"][:3],
                font=ctk.CTkFont(family=_BODY_FONT, size=11, weight="bold"),
                width=40, height=32, fg_color=style[0], hover_color=style[1],
                text_color=style[2], corner_radius=4,
                command=lambda k=key: self._pick_voice(k))
            btn.pack(side="left", padx=1)
            self.voice_btns[key] = btn
            self.voice_cards[key] = btn

        # Expand button
        ctk.CTkButton(row, text="\u2726",
            font=ctk.CTkFont(size=16, weight="bold"),
            width=32, height=32, fg_color=C_GOLD_DIM, hover_color=C_GOLD,
            text_color=C_VOID, corner_radius=4,
            command=lambda: self._apply_mode(self.MODE_FULL),
        ).pack(side="right", padx=2)

        ctk.CTkFrame(bar, fg_color=C_CRIMSON, height=1, corner_radius=0).pack(fill="x", side="bottom")

        # Dummy widgets for methods that reference them
        self.test_btn = ctk.CTkFrame(self)  # Hidden
        self.rec_btn = ctk.CTkFrame(self)
        self.stream_btn = ctk.CTkFrame(self)
        self.stream_mode = getattr(self, 'stream_mode', False)

    def _build_mini_vertical(self):
        """Vertical mini strip for docked left/right."""
        bar = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0)
        bar.pack(fill="both", expand=True)

        ctk.CTkFrame(bar, fg_color=C_GOLD, height=3, corner_radius=0).pack(fill="x")

        ctk.CTkLabel(bar, text="\u2620 TVOX",
            font=ctk.CTkFont(family=_TITLE_FONT, size=20, weight="bold"),
            text_color=C_GOLD_BRIGHT).pack(pady=(8, 4))

        self.voice_name = ctk.CTkLabel(bar, text="—",
            font=ctk.CTkFont(family=_TITLE_FONT, size=16, weight="bold"),
            text_color=C_GOLD_DIM)
        self.voice_name.pack(pady=(2, 4))

        self.voice_desc = ctk.CTkLabel(bar, text="", text_color=C_VOID)
        self.ind_bar = ctk.CTkFrame(bar, fg_color=C_BORDER, height=2, corner_radius=0)
        self.ind_bar.pack(fill="x", padx=4, pady=2)
        self.status = ctk.CTkLabel(bar, text="", text_color=C_VOID)
        self.latency_lbl = ctk.CTkLabel(bar, text="",
            font=ctk.CTkFont(family=_BODY_FONT, size=10), text_color=C_PARCHMENT_DIM)
        self.latency_lbl.pack(pady=2)
        self.voice_lbl = ctk.CTkLabel(bar, text="",
            font=ctk.CTkFont(family=_BODY_FONT, size=10, weight="bold"), text_color=C_PARCHMENT_DIM)
        self.voice_lbl.pack(pady=(0, 4))

        self.voice_btns = {}
        self.voice_cards = {}
        for i, (key, p) in enumerate(self.engine.presets.items()):
            style = VOICE_STYLE.get(key, (C_CARD, C_CARD_HOVER, C_GOLD))
            btn = ctk.CTkButton(bar, text=p["display_name"],
                font=ctk.CTkFont(family=_BODY_FONT, size=13, weight="bold"),
                height=44, fg_color=style[0], hover_color=style[1],
                text_color=style[2], corner_radius=4,
                command=lambda k=key: self._pick_voice(k))
            btn.pack(fill="x", padx=6, pady=2)
            self.voice_btns[key] = btn
            self.voice_cards[key] = btn

        ctk.CTkFrame(bar, fg_color=C_BORDER, height=1, corner_radius=0
            ).pack(fill="x", padx=6, pady=6)

        ctk.CTkButton(bar, text="FULL MODE",
            font=ctk.CTkFont(family=_BODY_FONT, size=12, weight="bold"),
            height=36, fg_color=C_GOLD_DIM, hover_color=C_GOLD,
            text_color=C_VOID, corner_radius=4,
            command=lambda: self._apply_mode(self.MODE_FULL),
        ).pack(fill="x", padx=6, pady=2)

        self.test_btn = ctk.CTkFrame(self)
        self.rec_btn = ctk.CTkFrame(self)
        self.stream_btn = ctk.CTkFrame(self)
        self.stream_mode = getattr(self, 'stream_mode', False)

    # Drag support for mini mode
    def _drag_start(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag_move(self, event):
        x = self.winfo_x() + event.x - self._drag_x
        y = self.winfo_y() + event.y - self._drag_y
        self.geometry(f"+{x}+{y}")

    # =================================================================
    # ACTIONS — what happens when you click things
    # =================================================================

    def _start_audio(self):
        self._set_status("Starting up... one moment...")
        if self.engine.start():
            self._pick_voice(list(self.engine.presets.keys())[0])
            self._set_status("Ready! Pick a voice and hit TEST MY VOICE to hear yourself.")
        else:
            self._set_status("Couldn't start audio — check your mic is plugged in, then hit HEAL AUDIO")

    def _pick_voice(self, key):
        """Select a voice preset."""
        if self.cycling:
            self._stop_cycle()
        # Stop stream during board swap to prevent race condition
        was_active = self.engine.is_active
        if was_active:
            self.engine.stop()
        self.engine.build_effects(key)
        if was_active:
            self.engine.start()
        self.active_key = key
        p = self.engine.presets[key]
        style = VOICE_STYLE.get(key, (C_CARD, C_CARD_HOVER, C_GOLD))

        self.voice_name.configure(text=p["display_name"], text_color=style[2])
        self.voice_desc.configure(text=p["description"], text_color=C_PARCHMENT)
        self.ind_bar.configure(fg_color=style[2])

        for k, card in self.voice_cards.items():
            try:
                if k == key:
                    card.configure(border_color=style[2], border_width=3)
                else:
                    card.configure(border_color=C_BORDER, border_width=2)
            except Exception:
                pass  # Mini/compact mode buttons don't have border_color

        self._set_status(f"Voice: {p['display_name']} — hit TEST MY VOICE to hear it!")
        self._sync_sliders_to_preset(key)

    def _sync_sliders_to_preset(self, key):
        """Update slider positions to match the current preset values."""
        if not self._sliders:
            return  # No sliders in compact/mini mode
        p = self.engine.presets[key]
        for param, (slider, val_label) in self._sliders.items():
            val = p.get(param, 0.0)
            slider.set(val)
            val_label.configure(text=f"{val:.1f}")

    def _on_slider(self, param, value, val_label):
        """Called when any slider moves — rebuild effects chain live."""
        val_label.configure(text=f"{value:.1f}")
        if self.active_key is None:
            return
        # Update the preset value in memory
        self.engine.presets[self.active_key][param] = float(value)
        # Rebuild effects chain with new value (stop/start for safety)
        was_active = self.engine.is_active
        if was_active:
            self.engine.stop()
        self.engine.build_effects(self.active_key)
        if was_active:
            self.engine.start()

    def _save_preset(self):
        """Save current slider values back to presets.json."""
        try:
            with open(PRESETS_FILE, "w") as f:
                json.dump(self.engine.presets, f, indent=2)
            self._set_status(f"Saved! {self.engine.presets[self.active_key]['display_name']} updated in presets.json")
        except Exception as e:
            self._set_status(f"Save failed: {e}")

    def _reset_sliders(self):
        """Reload preset from disk, discarding slider changes."""
        try:
            with open(PRESETS_FILE) as f:
                self.engine.presets = json.load(f)
            if self.active_key:
                self._pick_voice(self.active_key)
            self._set_status("Reset to saved preset values.")
        except Exception as e:
            self._set_status(f"Reset failed: {e}")

    def _test_voice(self):
        """Record 3s, process, play back. The 'wow' moment."""
        if self.stream_mode:
            self._set_status("Turn off STREAM MODE first — test plays through your headphones only.")
            return
        was_active = self.engine.is_active
        if was_active: self.engine.stop()
        self.test_btn.configure(text="SPEAK NOW! Recording for 3 seconds...",
                                fg_color=C_RED_BRIGHT)
        self._set_status("SPEAK NOW! Say something for 3 seconds...")
        self.update()

        def go():
            ok, msg = self.engine.test_my_voice(3.0)
            def done():
                self.test_btn.configure(
                    text="TEST MY VOICE — speak for 3 seconds and hear yourself!",
                    fg_color="#2a1a00")
                self._set_status(msg)
                if was_active: self.engine.start()
            self.after(0, done)
        threading.Thread(target=go, daemon=True).start()

    def _toggle_cycle(self):
        if not self.cycling:
            self.cycling = True
            self._cycle_idx = 0
            self.cycle_btn.configure(text="STOP — KEEP THIS VOICE",
                fg_color=C_RED_BRIGHT, hover_color="#e44",
                text_color=C_WHITE, border_color=C_RED_BRIGHT)
            self._cycle_next()
        else:
            self._stop_cycle()

    def _cycle_next(self):
        if not self.cycling: return
        keys = list(self.engine.presets.keys())
        key = keys[self._cycle_idx % len(keys)]
        self._pick_voice(key)
        self.cycling = True  # _pick_voice stops cycling, re-enable
        left = len(keys) - (self._cycle_idx % len(keys)) - 1
        self._set_status(f"Auditioning: {self.engine.presets[key]['display_name']}... "
                         f"({left} more) — hit STOP when you like one!")
        self._cycle_idx += 1
        self._cycle_timer = self.after(10000, self._cycle_next)

    def _stop_cycle(self):
        self.cycling = False
        if self._cycle_timer:
            self.after_cancel(self._cycle_timer); self._cycle_timer = None
        self.cycle_btn.configure(
            text="AUTO-CYCLE ALL VOICES (10s each) — hit STOP when you like one",
            fg_color="#140a20", hover_color="#201430",
            text_color="#b898d8", border_color="#4a3060")
        if self.active_key:
            name = self.engine.presets[self.active_key]["display_name"]
            self._set_status(f"Locked in: {name}! Hit TEST MY VOICE to hear it.")

    def _toggle_rec(self):
        if not self.recording:
            self.engine.start_recording()
            self.recording = True
            self.rec_btn.configure(text="STOP RECORDING", fg_color=C_RED_BRIGHT)
            self._set_status("Recording your god-voice... hit STOP RECORDING when done.")
        else:
            path = self.engine.stop_recording()
            self.recording = False
            self.rec_btn.configure(text="RECORD [F8]", fg_color=C_CRIMSON)
            self._set_status(f"Saved! File: {path}" if path else "Nothing recorded — try speaking louder.")

    def _toggle_stream_mode(self):
        """Switch output between headphones (hear yourself) and NGENUITY Chat (Discord hears you)."""
        self.stream_mode = not self.stream_mode

        if self.stream_mode:
            # Find NGENUITY Chat output device
            chat_idx = None
            for idx, name in self.outputs:
                if "ngenuity" in name.lower() and "chat" in name.lower():
                    chat_idx = idx; break

            if chat_idx is None:
                self._set_status("Can't find NGENUITY Chat device — is HyperX NGENUITY software running?")
                self.stream_mode = False
                return

            self.engine.output_device = chat_idx
            if self.engine.is_active:
                self.engine.stop(); self.engine.start()

            self.stream_btn.configure(
                text="STREAM MODE: ON — Discord/OBS hears your god-voice!",
                fg_color="#1a3000", hover_color="#2a4a08",
                text_color=C_GREEN, border_color=C_GREEN_DIM)
            self._set_status(
                "STREAM MODE ON! In Discord: set your mic to 'NGENUITY - Stream'. "
                "Your friends hear the god-voice now!")
        else:
            # Switch back to HyperX speakers (so YOU hear the voice again)
            self.engine.auto_pick_devices(self.inputs, self.outputs)
            if self.engine.is_active:
                self.engine.stop(); self.engine.start()

            self.stream_btn.configure(
                text="STREAM MODE: OFF — click to send god-voice to Discord/OBS",
                fg_color="#0a1420", hover_color="#142030",
                text_color="#6090c0", border_color="#203050")
            self._set_status("Stream mode off — audio back to your headphones.")

    def _heal(self):
        self._set_status("Fixing audio... one moment...")
        self.update()
        def go():
            ok = self.engine.heal()
            self.after(0, lambda: self._set_status(
                "Audio fixed! You're good to go." if ok else
                "Still broken — check your mic and speakers are plugged in."))
        threading.Thread(target=go, daemon=True).start()

    def _play_clip(self, filepath):
        self._set_status("Playing sound clip through your god-voice...")
        self.update()
        def go():
            ok = self.engine.play_soundclip(filepath)
            self.after(0, lambda: self._set_status(
                "Clip done! How'd that sound?" if ok else "Clip failed — check the file."))
        threading.Thread(target=go, daemon=True).start()

    def _easter_egg(self, event=None):
        """Claude Code stamp of approval — click 'For the Emperor' to reveal."""
        if not self._egg_revealed:
            self._egg_revealed = True
            self._egg_label.configure(
                text=(
                    "\u2620 FORGED BY CLAUDE CODE \u2022 OPUS 4.6 \u2620\n"
                    "AI + Human in the Loop \u2022 Loki speaks, Claude builds\n"
                    "ZK Proof Stream Ready \u2022 First of its kind\n"
                    "KHET-1 \u2022 lokidee \u2022 Anthropic\n"
                    "\u269C The Emperor Protects \u2022 Meow Meow \u269C"
                ),
                text_color=C_GOLD,
                font=ctk.CTkFont(family=_BODY_FONT, size=13, weight="bold"),
                justify="center")
            self._set_status("\u2620 Easter egg found! Claude Code stamp of approval revealed.")
        else:
            self._egg_revealed = False
            self._egg_label.configure(
                text="\u269C  For the Emperor  \u269C",
                text_color=C_GOLD_DIM,
                font=ctk.CTkFont(family=_BODY_FONT, size=13))

    def _set_status(self, text):
        self.status.configure(text=text)

    # =================================================================
    # BACKGROUND MONITOR — checks health + updates display + glow
    # =================================================================
    def _monitor(self):
        if self.engine.is_active:
            lat = self.engine.latency_ms
            lc = C_GREEN if lat < 40 else (C_GOLD if lat < 80 else C_RED_BRIGHT)
            self.latency_lbl.configure(text=f"Latency: {lat:.0f}ms", text_color=lc)
            if self.engine.voice_detected:
                self.voice_lbl.configure(text="\u2620 VOICE DETECTED", text_color=C_GREEN)
            else:
                self.voice_lbl.configure(text="listening...", text_color=C_PARCHMENT_DIM)
        if self.engine.needs_heal:
            self.engine.needs_heal = False
            self._heal()
        self.after(2000, self._monitor)
        # Subtle indicator pulse for stream visual
        self._pulse()

    _pulse_state = False
    def _pulse(self):
        """Subtle gold/crimson pulse on the voice indicator bar — looks alive on stream."""
        if not self.engine.is_active:
            return
        self._pulse_state = not self._pulse_state
        if self.active_key:
            style = VOICE_STYLE.get(self.active_key, (C_CARD, C_CARD_HOVER, C_GOLD))
            if self._pulse_state:
                self.ind_bar.configure(fg_color=style[2])
            else:
                self.ind_bar.configure(fg_color=C_GOLD_DIM)

    def _quit(self):
        self.engine.stop()
        try:
            with open(Path(__file__).parent / "fractal_faith_log.txt", "a") as f:
                f.write(f"\nSession: {datetime.datetime.now().isoformat()}\n")
                f.write(f"Preset: {self.engine.preset_name}\n")
                for e in self.engine.errors[-10:]: f.write(f"  {e}\n")
        except Exception: pass
        self.destroy()


# =====================================================================
# RUN IT
# =====================================================================
def main():
    print("\n  THUNDER_VOX — Voice of the God-Emperor\n")
    _setup_fonts()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    ThunderVoxApp().mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n{'!'*40}\nCRASHED: {e}\n{'!'*40}")
        traceback.print_exc()
        try:
            with open(Path(__file__).parent / "crash_log.txt", "a") as f:
                f.write(f"\n{datetime.datetime.now().isoformat()}\n{traceback.format_exc()}\n")
        except Exception: pass
        try: input("\nPress Enter to close...")
        except: pass
