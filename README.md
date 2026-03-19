<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:000000,50:1a1008,100:d4a017&height=200&section=header&text=THUNDER_VOX&fontSize=72&fontColor=ffd700&animation=fadeIn&fontAlignY=35&desc=VOICE%20OF%20THE%20GOD-EMPEROR&descSize=20&descAlignY=55&descColor=c8a832" width="100%"/>

**Real-time Warhammer 40k voice modulator for Windows**

*Sound like the Emperor, a Space Marine, a Chaos Lord, or an Ork — live on Discord, OBS, or just for fun.*

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-ffd700?style=flat-square)](LICENSE)
[![Built with Claude Code](https://img.shields.io/badge/Built_with-Claude_Code-CC785C?style=flat-square&logo=anthropic&logoColor=white)](https://claude.ai/claude-code)

</div>

---

## What is this?

**THUNDER_VOX** changes your voice in real-time to sound like characters from Warhammer 40,000. Talk into your mic, pick a voice, and you instantly sound different — deep booming Emperor, crackling Space Marine radio, scary Chaos echoes, crunchy Ork yelling, or a robotic Tech-Priest.

Works standalone (hear yourself through headphones) or with **Discord / OBS** for streaming.

---

## 7 Voice Presets

| Voice | What it sounds like |
|-------|-------------------|
| **Emperor God-King** | Super deep & booming — giant in a cathedral |
| **Space Marine** | Helmet radio crackle — walkie-talkie through ceramite |
| **Chaos Lord** | Scary cave echo — deep voice bouncing off dungeon walls |
| **Inquisitor** | Your voice but sharper — cold commanding authority |
| **Ork WAAAGH!!!** | Loud & crunchy — yelling through a broken megaphone |
| **Primaris Captain** | Deep & smooth — epic movie trailer narrator |
| **Tech-Priest** | Robot voice — pitched UP, thin & mechanical |

---

## Features

- **Big buttons, huge text** — designed for accessibility (tremor-friendly)
- **Auto-detects your headset** (HyperX, Razer, etc.)
- **TEST MY VOICE** — record 3 seconds, hear yourself transformed
- **Auto-cycle** — audition all 7 voices, stop when you like one
- **Stream Mode** — one click sends your god-voice to Discord/OBS
- **Soundboard** — drop MP3s into `sounds/` folder, play through effects
- **Record** — save your god-voice to WAV files
- **Self-healing** — auto-restarts if audio breaks
- **Hotkeys** — F1-F7 presets, F8 record, F9 heal, F12 test

---

## Install & Run

### What you need
- **Windows 10/11**
- **Python 3.10+** — [download here](https://python.org/downloads/) (check "Add to PATH")
- **A microphone** (any headset works)

### Quick start (easiest)

```
1. Download this repo (Code → Download ZIP → extract)
2. Double-click LAUNCH-GOD.bat
3. It installs everything and opens the app
```

### Command line

```powershell
cd C:\path\to\thundervox
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\python.exe main.py
```

---

## How to use

1. **Launch** — double-click `LAUNCH-GOD.bat`
2. **Pick a voice** — click any preset button (or press F1-F7)
3. **Test it** — click **TEST MY VOICE**, talk for 3 seconds, hear yourself
4. **Not sure which?** — click **AUTO-CYCLE**, it plays each voice for 10 seconds
5. **For Discord/OBS** — click **STREAM MODE**, set Discord mic to "NGENUITY - Stream"

---

## For Streamers (Discord / OBS)

1. Click **STREAM MODE: ON** in THUNDER_VOX
2. In Discord → Settings → Voice → Input Device → **"NGENUITY - Stream"**
3. Your friends hear the God-Emperor, not your normal voice

Works with any app that lets you pick a mic input.

---

## Soundboard

Drop `.mp3` or `.wav` files into the `sounds/` folder. They show up as buttons and play through your current voice effect.

---

## Customize a voice

Edit `presets.json` — the numbers that matter most:

| Setting | What it does | Range |
|---------|-------------|-------|
| `pitch_shift_semitones` | How deep (-) or high (+) | -12 to +12 |
| `distortion_drive_db` | Crunch/grit | 0 (clean) to 25 (nasty) |
| `reverb_wet_level` | Echo amount | 0.0 (dry) to 0.5 (cavern) |
| `gain_db` | Volume boost | 0 to 8 |

---

## Hotkeys

| Key | Action |
|-----|--------|
| F1-F7 | Switch voice presets |
| F8 | Record / Stop recording |
| F9 | Heal audio (fix glitches) |
| F12 | Test my voice (3s record + playback) |

---

## File Structure

```
thundervox/
├── main.py              ← The app
├── presets.json          ← Voice settings (edit to customize)
├── requirements.txt      ← Python packages
├── LAUNCH-GOD.bat        ← Double-click launcher
├── sounds/               ← Drop MP3/WAV here for soundboard
└── venv/                 ← Auto-created virtual environment
```

---

## Credits

**Built by [Loki](https://github.com/lokidee)** — struck by lightning twice, still louder than thunder. Uses Claude Code as his hands.

**Mentored by [KHET-1](https://github.com/KHET-1)** — veteran game developer, 173+ shipped titles.

**Powered by:**
- [pedalboard](https://github.com/spotify/pedalboard) by Spotify — audio effects
- [customtkinter](https://github.com/TomSchimansky/CustomTkinter) — GUI
- [Claude Code](https://claude.ai/claude-code) by Anthropic — AI pair programming

---

<div align="center">

*"The Emperor protects — and Claude Code types."*

**For the Emperor. Meow meow.**

⚡ *Disability doesn't stop creation — it just changes the path.* ⚡

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:000000,50:1a1008,100:d4a017&height=100&section=footer" width="100%"/>

</div>
