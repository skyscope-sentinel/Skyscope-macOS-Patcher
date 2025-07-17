# Contributing to **Skyscope macOS Patcher**

:tada: Thanks for your interest in helping make unsupported Macs faster (and shinier)! This guide explains how to contribute code, documentation, testing, and ideas to the project while keeping the repository healthy and maintainable.

---

## 1. Code of Conduct

Be kind, be constructive, be inclusive. We follow the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) (implicit). Harassment, hate speech, or personal attacks will not be tolerated.

---

## 2. Getting Started

1. **Fork** the repo on GitHub and clone your fork:

   ```bash
   git clone https://github.com/<your-user>/Skyscope-macOS-Patcher.git
   cd Skyscope-macOS-Patcher
   git remote add upstream https://github.com/skyscope-cloud/Skyscope-macOS-Patcher.git
   ```

2. **Install prerequisites** (macOS 14+):

   ```bash
   xcode-select --install           # Command-line tools
   brew install python@3.11 git
   ./skyscope_unified_compiler.sh   # Will auto-install Python deps
   ```

3. **Create a feature branch**:

   ```bash
   git checkout -b feat/<short-topic>
   ```

---

## 3. Code Style Guidelines

| Language | Lint / Formatter | Rules |
|----------|-----------------|-------|
| **Python** (`*.py`) | `ruff`, `black` | 120-char lines, type hints required in new code, f-strings over `%` or `.format()` |
| **Bash**  (`*.sh`) | `shellcheck`     | POSIX + Bash 5; avoid `set +e`; prefer functions; descriptive flags |
| **C/C++** (`*.cpp`, `*.hpp`) | `clang-format` (LLVM style) | Tabs = 4 spaces; explicit `std::` namespaces; RAII; no raw `new`/`delete` |
| **JSON / Plist** | `prettier` plugins | 2-space indent; trailing commas *disabled* |

Run `make lint` before committing; CI will fail on style violations.

---

## 4. Pull Request Process

1. **Sync** with upstream regularly:

   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Commit etiquette**

   * Use present-tense imperative: “Add Metal shader cache”, not “Added”.
   * Group logical changes; avoid commits that mix refactors and features.
   * Sign-off (`git commit -s`) if contributing under DCO.

3. **Open the PR**

   * Fill in the template: motivation, approach, testing, related issues.
   * For GPU driver work, attach `ioreg` dumps and `kextstat` output.
   * Draft PRs are welcome for early feedback.

4. **Reviews & CI**

   * GitHub Actions will run **build**, **lint**, and **unit tests** on macOS.
   * At least one maintainer approval + green CI required before merge.
   * Squash-merge is the default; request a rebase if history matters.

---

## 5. Building the Project

| Task | Command |
|------|---------|
| Interactive build | `./skyscope_unified_compiler.sh` |
| Non-interactive build | `./skyscope_unified_compiler.sh --build` |
| Install artifacts   | `./skyscope_unified_compiler.sh --install` |
| Clean | `./skyscope_unified_compiler.sh --clean` |

The script:

1. Verifies Python ≥ 3.8 and installs missing packages (`wxPython`, `pyinstaller`, `lief`, …).
2. Downloads or updates **OpenCore-Legacy-Patcher** sources inside `RESOURCES/`.
3. Injects Skyscope patches (`constants.py`, GPU bridges, beta OS spoof).
4. Builds `Skyscope macOS Patcher.app` and a signed/unsigned DMG in `output/`.

Tip: Use `export SKYSCOPE_DEBUG=1` for verbose logs (`~/skyscope_build.log`).

---

## 6. Testing Requirements

### 6.1 Unit & Integration Tests

* Python tests live in `tests/` and run with `pytest`.
* Use `pytest-mypy-plugins` for type-checking fixtures.
* Add tests for:
  * CLI argument parsing
  * JSON config loading
  * Version-spoof logic (`os_probe.py` patch)
  * Kext path resolution

Run locally:

```bash
python -m pip install -r tests/requirements.txt
pytest -q
```

### 6.2 Hardware Validation Matrix

GPU / macOS combos must be smoke-tested:

| GPU | Sonoma | Sequoia | Tahoe | Beta 26.x |
|-----|--------|---------|-------|-----------|
| GTX 970 | ✅ | ✅ | ✅ | ✅ |
| Arc A770 | ✅ | ✅ | ✅ | ✅ |

Post results in the PR description with:

```text
System: i7-12700K + Arc A770
Build: 26.2 (22C123)
Status: Boot OK, Metal OK, H.264 OK, AV1 OK
```

Attach `/var/log/SkyscopePatch.log` and `kextstat`.

---

## 7. Best Practices for GPU Driver & macOS Integration

1. **Don’t ship binary blobs** – provide build scripts or submodules pointing to source.
2. **Keep KEXT bundle IDs unique** (`com.skyscope.driver.*`) to avoid clobbering vendor kexts.
3. **Respect SIP settings** – patches should work with “Reduced Security” when possible.
4. **Use Lilu plugins** where feasible; avoid patching Apple binaries in-place.
5. **Log verbosely** but redact serial numbers and user paths (`~/`).
6. **Resizable BAR & Above 4G**: document BIOS toggles in PR if feature depends on them.
7. **Code signing**: test both ad-hoc and Developer ID-signed builds; use `--entitlements`.
8. **Kernel stability**: boot with `debug=0x100 keepsyms=1 -v` on first run to capture KP traces.

---

## 8. Documentation Contributions

* Docs live at repository root (`README.md`, `docs/`, JSON schemas).
* For **README** or **advanced_config.json** updates, open docs-only PRs.
* Use Markdown headings ≤ H3, keep line length ≤ 100 chars.
* Screenshots: PNG, ≤ 1 MB, placed in `docs/assets/`.
* Diagram sources must be in `*.drawio` or `*.svg` for easy editing.

---

## 9. Helpful Resources

* **OpenCore-Legacy-Patcher Guide** – https://dortania.github.io/OpenCore-Legacy-Patcher/
* **Apple Kernel Extensions Programming Guide** – https://developer.apple.com
* **Metal Shading Language Spec** – https://developer.apple.com/metal/
* **Acidanthera Lilu Wiki** – https://github.com/acidanthera/Lilu
* **Olarila Forums (Testing)** – https://www.olarila.com
* **Discord** – join `#OCLP-Patcher-Paradise` for real-time help.

---

## 10. Frequently Asked Questions

<details>
<summary>Q: The build script fails on `wxPython`.</summary>

wxPython wheels lag behind new macOS SDKs. Try:

```bash
pip install -U pip wheel setuptools
ARCHFLAGS="-arch arm64 -arch x86_64" pip install wxPython==4.2.1
```

or `brew install wxpython`.
</details>

<details>
<summary>Q: Kernel panic after installing ArcBridge.kext.</summary>

Boot with `keepsyms=1 debug=0x100` and attach the panic log to your issue. Check that Resizable BAR is **enabled** in BIOS.
</details>

---

Happy hacking! :rocket:
