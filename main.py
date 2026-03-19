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
        """Build the voice effect chain from a preset. Called when you pick a voice."""
        p = self.presets[preset_key]
        self.preset_name = preset_key
        self.board = Pedalboard([
            # Gate: blocks background noise when you're not talking
            NoiseGate(threshold_db=-50.0, ratio=2.0, release_ms=120.0),
            # Pitch: shifts your voice up or down
            PitchShift(semitones=p["pitch_shift_semitones"]),
            # EQ: boosts bass (low shelf) or treble (high shelf)
            LowShelfFilter(cutoff_frequency_hz=p["low_shelf_cutoff_hz"],
                           gain_db=p["low_shelf_gain_db"]),
            HighShelfFilter(cutoff_frequency_hz=p["high_shelf_cutoff_hz"],
                            gain_db=p["high_shelf_gain_db"]),
            # Distortion: adds grit/crunch (0 = clean, higher = dirtier)
            Distortion(drive_db=p["distortion_drive_db"]),
            # Compressor: evens out loud/quiet (makes it radio-ready)
            Compressor(threshold_db=p["compressor_threshold_db"],
                       ratio=p["compressor_ratio"]),
            # Gain: overall volume boost
            Gain(gain_db=p["gain_db"]),
            # Reverb: echo/room sound (0 = dry, higher = more echo)
            Reverb(room_size=p["reverb_room_size"],
                   wet_level=p["reverb_wet_level"],
                   damping=p["reverb_damping"]),
        ])

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

    def __init__(self):
        super().__init__()

        # Window setup
        self.title("THUNDER_VOX")
        self.geometry("1100x1000")
        self.minsize(900, 750)
        self.configure(fg_color=C_VOID)

        # Create the voice engine
        self.engine = VoiceEngine()
        self.recording = False
        self.active_key = None
        self.cycling = False
        self._cycle_timer = None

        # Find audio devices and auto-pick the best ones
        self.inputs, self.outputs = self.engine.find_devices()
        self.engine.auto_pick_devices(self.inputs, self.outputs)

        # Build the interface
        self._build_ui()

        # Auto-start if we have devices
        if self.inputs and self.outputs:
            self.after(500, self._start_audio)

        # Health monitor
        self._monitor()
        self.protocol("WM_DELETE_WINDOW", self._quit)

    # =================================================================
    # BUILD THE INTERFACE
    # =================================================================
    def _build_ui(self):
        # Scrollable main area
        self.main = ctk.CTkScrollableFrame(self, fg_color=C_VOID,
            scrollbar_button_color=C_GOLD_DIM,
            scrollbar_button_hover_color=C_GOLD)
        self.main.pack(fill="both", expand=True)

        # ── HEADER ──────────────────────────────────────────
        hdr = ctk.CTkFrame(self.main, fg_color=C_PANEL, corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkFrame(hdr, fg_color=C_GOLD, height=4, corner_radius=0).pack(fill="x")

        pad = ctk.CTkFrame(hdr, fg_color="transparent")
        pad.pack(fill="x", padx=28, pady=(20, 6))

        ctk.CTkLabel(pad, text="THUNDER_VOX",
            font=ctk.CTkFont(family=_TITLE_FONT, size=F_HUGE, weight="bold"),
            text_color=C_GOLD_BRIGHT).pack(anchor="w")

        ctk.CTkLabel(pad, text="VOICE OF THE GOD-EMPEROR",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_MED, weight="bold"),
            text_color=C_CRIMSON).pack(anchor="w")

        ctk.CTkFrame(hdr, fg_color=C_GOLD_DIM, height=1, corner_radius=0).pack(fill="x", pady=(10,0))

        # Welcome / status
        status_pad = ctk.CTkFrame(hdr, fg_color="transparent")
        status_pad.pack(fill="x", padx=28, pady=(8, 14))

        self.status = ctk.CTkLabel(status_pad,
            text="Welcome! Pick a voice below, then hit TEST MY VOICE to hear yourself.",
            font=ctk.CTkFont(family=_BODY_FONT, size=F_NORM),
            text_color=C_PARCHMENT, wraplength=900, justify="left")
        self.status.pack(anchor="w")

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

        # ── MAIN BUTTONS ────────────────────────────────────
        ctk.CTkFrame(self.main, fg_color=C_BORDER, height=1, corner_radius=0
            ).pack(fill="x", padx=24, pady=(12, 0))

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

        # Bottom spacer
        ctk.CTkFrame(self.main, fg_color=C_VOID, height=20, corner_radius=0).pack(fill="x")

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
            if k == key:
                card.configure(border_color=style[2], border_width=3)
            else:
                card.configure(border_color=C_BORDER, border_width=2)

        self._set_status(f"Voice: {p['display_name']} — hit TEST MY VOICE to hear it!")

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

    def _set_status(self, text):
        self.status.configure(text=text)

    # =================================================================
    # BACKGROUND MONITOR — checks health + updates display
    # =================================================================
    def _monitor(self):
        if self.engine.is_active:
            lat = self.engine.latency_ms
            lc = C_GREEN if lat < 40 else (C_GOLD if lat < 80 else C_RED_BRIGHT)
            self.latency_lbl.configure(text=f"Latency: {lat:.0f}ms", text_color=lc)
            if self.engine.voice_detected:
                self.voice_lbl.configure(text="VOICE DETECTED", text_color=C_GREEN)
            else:
                self.voice_lbl.configure(text="listening...", text_color=C_PARCHMENT_DIM)
        if self.engine.needs_heal:
            self.engine.needs_heal = False
            self._heal()
        self.after(2000, self._monitor)

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
