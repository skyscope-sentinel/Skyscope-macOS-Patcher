# Skyscope macOS Patcher – Design Document  
*(Developer: _Miss Casey Jay Topojani_)*  

---

## 1 . Introduction & Overview
Skyscope macOS Patcher (SMP) is a dark-themed, self-contained `.app` and command-line toolkit that automates installation and post-install patching of macOS Sequoia (15) and macOS Tahoe betas on unsupported or custom hardware.  
Key goals:  

* One-click build of a shrink-optimized macOS installer (-300 MB)  
* Automatic hardware audit → tailored OpenCore EFI & `config.plist`  
* Best-possible GPU acceleration, including experimental NVIDIA Web-Driver bridge for Maxwell cards (GTX 970) on 15.x/16.x  
* Support for modern Intel platforms (Alder Lake, Raptor Lake, Arc 770 iGPU) and legacy Macs alike  
* Distributable as signed `.dmg` or notarized `.app`

---

## 2 . High-Level Architecture
```
┌─────────────────────────────────────────────────┐
│  Skyscope.app  (wxPython & PyObjC dark UI)      │
│                                                 │
│  ├─ Core Orchestrator (Python 3.12)             │
│  │   • State machine & logging                  │
│  ├─ Hardware Detection Service                  │
│  ├─ OpenCore Builder (wrapping Acidanthera)     │
│  ├─ Driver/Kext Manager                         │
│  ├─ Installer Shrinker                          │
│  └─ ISO/IMG Creator & USB Writer                │
└─────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────┐
│   Payloads/                                   │
│   ├─ OpenCorePkg git submodule (tag pin)       │
│   ├─ NVIDIA bridge kexts & frameworks          │
│   ├─ Lilu ‑ WhateverGreen ‑ RestrictEvents     │
│   └─ Apple OEM resources (extracted locally)   │
└─────────────────────────────────────────────────┘
```
Communication: pure filesystem + `subprocess`, no elevated permissions until “Build & Install EFI/USB” step (then ask for sudo).

---

## 3 . Hardware Detection Module
Implementation: `skyscope/hwprobe/*.py`

* Reads ACPI tables (`ioreg -l`, `dmidecode`, `/sys` on Linux)  
* GPU census via PCI IDs → maps to known DB (`pcidb.json`)  
* CPU family, microcode revision, core count, E/P-core ratio  
* Chipset & motherboard vendor (SMBus + SMBIOS)  
* Firmware modality (UEFI vs legacy CSM) and Secure-Boot toggles  
* Produces a typed `MachineProfile` dataclass consumed by downstream generators.

Accuracy tiers:  
1. **Native** – running under macOS environment  
2. **Fallback** – Live-Linux probing when user only has Windows (ships minimal Debian image + Python)  

---

## 4 . OpenCore Integration & Bootloader Configuration
* Vendored OpenCorePkg (pinned to latest stable tag, e.g. 1.0.5)  
* Compile through `build_oc.tool` inside dockerized `edk2` image (`ghcr.io/skyscope/oc-build:latest`).  
* `ConfigGenerator` class maps `MachineProfile` → `config.plist`:  
  * Picks proper SMBIOS (`iMacPro1,1` for dGPU systems, `Mac14,3` for Arc 770, etc.)  
  * Enables `Kernel → Quirks` for Alder/Raptor (Kernel-XCPM, ShutdownFix).  
  * DeviceProperties injection for GPUs (Nvidia NVCAP spoof, Arc `AAPL,ig-platform-id` 0x0a00601).  
  * Automatic `UEFISecureBoot` → `False` if firmware unsupported.  
* Generates a FAT32 EFI structure, adds `BOOTx64.efi`, driver set (OpenCanopy, HfsPlus, UsbKbDxe).  

---

## 5 . NVIDIA Driver Support (Sequoia & Tahoe)
* Ships **Skyscope-NVBridge.kext**: wrapper that re-exports expected symbols removed after Big Sur and forwards to internal Metal Shaders.  
* On-the-fly patching:  
  * Injects Maxwell device-IDs into `NVDAStartupWeb`, forces `nv_web` personality.  
  * Adds `com.apple.private.GPUOverride` entitlement via Lilu plug-in.  
* CUDA 12.9.1 repo installation (mirrors NVIDIA deb → extracts fat-binary libs).  
* Performs SIP-safe rootless patches using Apple’s cryptex overlay method (same used by OCLP).  
* Fallback to VESA if bridge fails, with UI warning banner.  

---

## 6 . Dark-Themed UI
Stack: **wxPython 4.2** + **native NSAppearance** (PyObjC)  
Branding: Blue-violet gradient (#22203A → #3C5FA8), accent color cyan.  

Screens:  
1. Welcome & EULA  
2. Hardware Summary (traffic-light compatibility indicators)  
3. “Build Installer” wizard (choose Sequoia/Tahoe dmg, size shrink, create USB)  
4. “Post-Install Patching” (drivers, EFI updates)  
5. Advanced → OpenCore Config Editor (tree + diff)  

Accessibility: VoiceOver labels, high-contrast toggle.

---

## 7 . Build System
* **Python poetry** monorepo → wheels for core libs.  
* Makefile tasks:  
  * `make bootstrap` – fetch submodules, create venv  
  * `make oc` – containerized OpenCore build  
  * `make app` – PyInstaller one-file `.app` bundle  
  * `make dmg` – create notarized disk-image via `dmgbuild`  
* CI: GitHub Actions matrix macOS-14 & ubuntu-24.04 (for cross-compile of EFI).  
* Release channel tagging: `nightly-dev`, `beta`, `stable`.

---

## 8 . Advanced Features
### 8.1 Installer Shrinker  
* Removes non-English language packs, bundled Xcode stubs, and legacy i386 slices → average 300 MB saved.  
* Done with `pkgutil --expand` / `ditto --rsrc --arch`.  

### 8.2 Bootable EFI / USB Creator  
* `diskutil eraseDisk FAT32 SKYSCOPE MBR /dev/diskX`  
* Copies compiled EFI, blesses with `bootx64.efi`, sets startup disk for Mac targets (`bless --folder`).

### 8.3 Live Update & Self-heal  
* Embedded Sparkle feed or CLI `skyscope self-update`.  
* EFI diff-merge engine preserves user edits (3-way merge with trust score).  

---

## 9 . Hardware-Specific Optimizations
| Hardware | Tweaks applied |
|-----------|----------------|
| **NVIDIA GTX 970 (GM204)** | Maxwell personality injection, disable ASPM, memory-remap quirk, DPR-offload for high-DP monitors |
| **Intel i7/i9 9xxx-14xxx (desktop)** | CPUFriendDataProvider generation, enables HWP & XCPM, sets PowerLimit TDP=125 W |
| **Alder Lake (12th Gen)** | EC Sync via ECEnabler, E-core mask for macOS ≤ 15, P-core Turbo tables |
| **Raptor Lake (13th/14th Gen refresh)** | Updated microcode bundle, Native IGPU `ig-platform-id` 0x0a00406, Resizable-BAR toggle |
| **Intel Arc 770 iGPU/dGPU** | Overrides `AAPL,Gfx324` property, loads `AGXArcMetal13` frameworks, sets DVMT 64 MB → 512 MB patch |

---

### Appendix: Terminology
* **OCLP** – OpenCore Legacy Patcher; reference project inspiration.  
* **NVBridge** – Skyscope’s Lilu plug-in bridging removed NV symbols.  
* **Shrink-PKG** – internal module performing installer deflation.

*Last updated: 2025-07-09*  
