<!-- Centered Logo -->
<p align="center">
  <img src="Resources/logo.png" alt="Skyscope macOS Patcher" width="280"/>
</p>

<h1 align="center">Skyscope macOS Patcher</h1>

<p align="center">
  Unified OpenCore-based patcher bringing native NVIDIA GTX 970 &amp; Intel Arc A770 acceleration<br/>
  to macOS Sequoia, Tahoe and the 26.x beta cycle — wrapped in a single automated build script.
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/build-passing-brightgreen?style=flat-square"/></a>
  <a href="#"><img src="https://img.shields.io/github/license/skyscope-cloud/Skyscope-macOS-Patcher?style=flat-square"/></a>
  <a href="#"><img src="https://img.shields.io/github/v/release/skyscope-cloud/Skyscope-macOS-Patcher?style=flat-square"/></a>
  <a href="#"><img src="https://img.shields.io/github/last-commit/skyscope-cloud/Skyscope-macOS-Patcher?style=flat-square"/></a>
</p>

---

## ✨ Key Features
* **Native GPU Acceleration**
  * NVIDIA **GeForce GTX 970** (Maxwell, 4 GB) – Metal 3, CUDA, VideoToolbox  
  * Intel **Arc A770** (Xe-HPG, 16 GB) – Metal 3, XMX, AV1/HEVC HW decode  
* **macOS Beta Compatibility** – seamless operation on 26.0 → 26.3 betas with version-spoofing patches.
* **Single Unified Script** – `skyscope_unified_compiler.sh` automates dependencies, patches OCLP, compiles GUI, creates DMG and installs custom kexts.
* **Cross-Platform GUI** – PyInstaller‐built `.app`, `.dmg`, `.exe`, `.AppImage` artefacts.
* **Professional Documentation & CI-ready build system**.

---

## 📦 Requirements
* macOS 14 (Sonoma) or newer host for building  
* Xcode CLT, Python ≥ 3.8  
* 10 GB free disk space  
* Supported hardware (see matrix below)

---

## 🚀 Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/skyscope-cloud/Skyscope-macOS-Patcher.git
cd Skyscope-macOS-Patcher

# 2. Build (installs dependencies automatically)
./skyscope_unified_compiler.sh --build    # or simply `./skyscope_unified_compiler.sh`

# 3. Install (optional step if you skipped the prompt)
./skyscope_unified_compiler.sh --install
```

After completion you will find:

* `output/Skyscope macOS Patcher.app`
* `output/Skyscope macOS Patcher.dmg`

---

## 🖥️ GPU Support Matrix

| Vendor  | Model                       | Architecture | Metal | Video Decode | Notes |
|---------|----------------------------|--------------|-------|--------------|-------|
| NVIDIA  | GeForce GTX 970            | Maxwell      | ✅    | H264/HEVC    | Full acceleration via **NVBridge.kext** |
| NVIDIA  | GeForce GTX 980 Ti / 10-series (*experimental*) | Maxwell / Pascal | ✅ | H264/HEVC | Same driver path as GTX 970 |
| Intel   | Arc A770                   | Xe-HPG       | ✅    | H264/HEVC/AV1| **ArcBridge.kext** with XMX support |
| Intel   | Arc A750 / A580 / A380     | Xe-HPG       | ✅    | H264/HEVC/AV1| Experimental |

---

## 🧪 macOS 26.x Beta Compatibility
The patcher injects custom logic into OpenCore-Legacy-Patcher to recognise and spoof the following pre-release versions:

| Marketing Name | Product Version | Build Prefix |
|----------------|-----------------|--------------|
| macOS Beta     | 26.0            | 26A |
| macOS Beta 1   | 26.1            | 26B |
| macOS Beta 2   | 26.2            | 26C |
| macOS Beta 3   | 26.3            | 26D |

---

## 🛠️ Script Usage

| Flag          | Description                                   |
|---------------|-----------------------------------------------|
| `--build`     | Build patcher, DMG and custom kexts           |
| `--install`   | Install app and kexts to `/Applications` & `/Library/Extensions` |
| `--clean`     | Remove build artefacts                        |
| `--help`      | Show usage information                        |

---

## 🤝 Partnership

| Partner | Link | Role |
|---------|------|------|
| ![Olarila Logo](Resources/olarila_logo.png) | [olarila.com](https://www.olarila.com) | Community partner providing Hackintosh testing & support |

We proudly collaborate with **Olarila**, the trusted Hackintosh community, to validate real-world compatibility and provide user support channels.

---

## 📚 Documentation
* [Advanced Configuration](advanced_config.json)
* [Developer Guide](CONTRIBUTING.md)
* [Changelog](CHANGELOG.md) *(coming soon)*

---

## 🙌 Contributing
Pull requests are welcome! Please read **CONTRIBUTING.md** for style guidelines, code-signing instructions and preferred commit structure.

---

## ⚖️ License
This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

---

## 🎉 Acknowledgements
* **Dortania** – OpenCore-Legacy-Patcher foundation  
* **Acidanthera** – Lilu, WhateverGreen, OpenCore  
* **Apple** – macOS & Metal framework  
* **Community Testers** – Olarila, Discord **#OCLP-Patcher-Paradise**  
