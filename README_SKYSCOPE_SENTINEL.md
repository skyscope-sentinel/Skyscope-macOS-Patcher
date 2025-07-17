# Skyscope Sentinel Intelligence Patcher  
_Bringing next-gen GPU & hardware support to macOS Sequoia, Tahoe and beyond_

![Skyscope Sentinel Logo](docs/images/skyscope_logo_dark.png)

**Developer:** Casey Jay Topojani  
**Version:** 1.0.0  **Identifier:** `com.skyscope.sentinel.patcher`

---

## 1 What Is This?

Skyscope Sentinel Intelligence Patcher (SSIP) is a heavily-customised fork of OpenCore Legacy Patcher that adds:

* Native Metal acceleration for **NVIDIA Maxwell/Pascal (GTX 970, 980, 10-Series)**  
* Native Metal acceleration for **Intel Arc A-series (A380, A750, A770)**  
* Automated **audio-codec** patching (Realtek **ALC897** preset)  
* Smart **boot-arguments manager** (deduplicates & merges args)  
* **Dark-theme GUI** with Skyscope branding  
* **Root-patch engine** extended for macOS β-releases 26.0 – 26.3 and future 27+  
* One-click USB installer / DMG creator and cross-platform builds (.app / .dmg / .zip)

The goal is simple: run the latest macOS betas on unsupported hardware **with full graphics, audio and system stability**.

---

## 2 Feature Highlights

| Area | Enhancement |
|------|-------------|
| **GPU** | • GTX 970/980/10-Series full Metal via `nvbridge_core` & `nvbridge_metal`  <br>• Intel Arc A-series full Metal & XMX via `arc_bridge` |
| **Kexts** | Auto-build & inject custom bridge kexts, WEG patches and `AppleIntelArc*.kext` hooks |
| **Audio** | ALC897 auto-detect, adds `alcid=12`, copies AppleALC layout, injects codec resources |
| **Boot Args** | Default string: `alcid=12 watchdog=0 agdpmod=pikera e1000=0 npci=0x3000 -wegnoigpu`  + optional custom merge |
| **macOS Beta** | Kernel major 24 – 26 recognised; enhanced root-patch path for > Sequoia |
| **GUI** | wxPython dark mode, Skyscope colour palette, dynamic title “Developer: Casey Jay Topojani” |
| **Build System** | Single script `skyscope_sentinel_compiler.sh` handles deps ➜ patch ➜ PyInstaller ➜ DMG |
| **Cross-Platform** | Output `.app`, `.dmg`, or `.zip`; Windows & Linux builds via separate CI job |

---

## 3 Prerequisites

* Build host: **macOS 14 Sonoma** or newer (Intel or Apple Silicon)  
* **Xcode Command-Line Tools** (`xcode-select --install`)  
* **Python ≥ 3.8** (system or Anaconda)  
* ≥ 10 GB free disk space & reliable internet  
* **Homebrew** optional (used only as wxPython fallback)  

> The script auto-installs `pyinstaller`, `wxPython 4.2.1`, `dmgbuild`, `lief`, etc.  
> Anaconda environments are detected and handled gracefully.

---

## 4 Quick Start

```bash
# Clone project
git clone https://github.com/YourUser/Skyscope-macOS-Patcher.git
cd Skyscope-macOS-Patcher

# Build
./skyscope_sentinel_compiler.sh --build          # ~15-25 min first run

# (optional) Install to /Applications + copy kexts
./skyscope_sentinel_compiler.sh --install

# Clean artefacts
./skyscope_sentinel_compiler.sh --clean
```

Outputs are placed in `output/`:

* `Skyscope Sentinel Intelligence Patcher.app`
* `Skyscope Sentinel Intelligence Patcher.dmg` _(or .zip fallback)_

---

## 5 Using the App

1. Launch the `.app` — dark-theme GUI appears.  
2. Hardware is probed automatically; unsupported GPUs show a **“Patch”** button.  
3. Click **Create Installer** to build a USB or **Build & Install Root Patches** to patch live system.  
4. Reboot when prompted.

Advanced panels expose:

* GPU override selector & Metal test
* Boot-argument editor (merges with defaults)
* Kext debug switch / OpenCore picker settings
* Root-patch **force** mode for macOS 26.x+

---

## 6 Troubleshooting

• **wxPython fails to compile** – ensure Xcode CLT is installed, or let the script fallback to Homebrew bottle.  
• **Installer hangs at “patching root”** – disable SIP entirely or ensure authenticated-root is disabled.  
• **No display after boot** – add `agdpmod=pikera` for AMD dGPUs, toggle “Force Output Support” in GUI.  
• **NVIDIA web driver prompt** – not required; SSIP replaces them with custom bridge kext.  
• Full logs: `~/skyscope_build.log` and program menu **Help ➜ Show Logs**.

---

## 7 Development & Contributions

Contributions are welcome!  
See **CONTRIBUTING.md** for code style, branching model and CI info.

---

## 8 License

Skyscope Sentinel Intelligence Patcher is released under the **MIT License**.  
Portions derived from OpenCore Legacy Patcher (© Dortania 2020-2025).  

See **LICENSE** for full text.
