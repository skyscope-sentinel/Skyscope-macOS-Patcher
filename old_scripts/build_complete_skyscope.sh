#!/bin/bash
#
# build_complete_skyscope.sh
# Skyscope macOS Patcher - Build and Installation Script
#
# Compiles and installs all components of the Skyscope macOS Patcher
# for enabling NVIDIA GTX 970 and Intel Arc A770 support in macOS Sequoia and Tahoe
#
# Developer: Miss Casey Jay Topojani
# Version: 1.0.0
# Date: July 9, 2025
#

# Set strict error handling
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# Script variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BUILD_DIR="${SCRIPT_DIR}/build"
KEXTS_DIR="${SCRIPT_DIR}/resources/Kexts"
SRC_DIR="${SCRIPT_DIR}/src"
OUTPUT_DIR="${SCRIPT_DIR}/output"
TEMP_DIR="${BUILD_DIR}/temp"
# Log file goes to user’s home directory to avoid permission issues
LOG_FILE="${HOME}/skyscope_build.log"
VERSION="1.0.0"
BUILD_DATE="July 9, 2025"

# Kext bundle identifiers
NVBRIDGE_BUNDLE_ID="com.skyscope.NVBridgeCore"
NVBRIDGE_METAL_BUNDLE_ID="com.skyscope.NVBridgeMetal"
NVBRIDGE_CUDA_BUNDLE_ID="com.skyscope.NVBridgeCUDA"
ARCBRIDGE_BUNDLE_ID="com.skyscope.ArcBridgeCore"
ARCBRIDGE_METAL_BUNDLE_ID="com.skyscope.ArcBridgeMetal"

# Function to display banner
show_banner() {
    echo -e "${BLUE}${BOLD}"
    echo "=============================================================================="
    echo "                     Skyscope macOS Patcher Builder v${VERSION}                "
    echo "                                ${BUILD_DATE}                                  "
    echo "=============================================================================="
    echo -e "${RESET}"
    echo "This script will build and install the Skyscope macOS Patcher"
    echo "for NVIDIA GTX 970 and Intel Arc A770 support in macOS Sequoia and Tahoe"
    echo ""
}

# Function for logging
log() {
    local message="$1"
    local level="$2"
    local color="${RESET}"
    
    case "$level" in
        "INFO") color="${GREEN}" ;;
        "WARNING") color="${YELLOW}" ;;
        "ERROR") color="${RED}" ;;
        "STEP") color="${CYAN}${BOLD}" ;;
    esac
    
    # Log to console
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] ${message}${RESET}"
    
    # Log to file
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] ${message}" >> "${LOG_FILE}"
}

# Function to check if running as root
# ----------------------------------------
#  Some steps (Homebrew, building, etc.)
#  MUST run as the regular user because
#  Homebrew refuses to operate as root.
#  The sections that truly need privilege
#  (kext copy, chmod/chown, nvram write,
#  kextcache) dynamically request sudo.
# ----------------------------------------

# Abort early if the user invoked the whole
# script with sudo/root – that breaks Brew.
check_not_root() {
    if [ "$EUID" -eq 0 ]; then
        log "ERROR: Do NOT run this script with sudo." "ERROR"
        log "Homebrew cannot run as root. Please re-run without sudo." "ERROR"
        exit 1
    fi
}

# Cache sudo credentials when required
prompt_for_sudo() {
    if ! sudo -n true 2>/dev/null; then
        echo
        log "Administrator privileges are required for the next step." "WARNING"
        log "You may be prompted for your password..." "WARNING"
        sudo -v || { log "Failed to obtain sudo privileges." "ERROR"; exit 1; }
    fi
    # refresh sudo timestamp while we work
    sudo -n true 2>/dev/null
}

# Function to create directories
create_directories() {
    log "Creating build directories" "STEP"
    mkdir -p "${BUILD_DIR}"
    mkdir -p "${KEXTS_DIR}"
    mkdir -p "${OUTPUT_DIR}"
    mkdir -p "${TEMP_DIR}"
    mkdir -p "${KEXTS_DIR}/NVBridgeCore.kext/Contents/MacOS"
    mkdir -p "${KEXTS_DIR}/NVBridgeMetal.kext/Contents/MacOS"
    mkdir -p "${KEXTS_DIR}/NVBridgeCUDA.kext/Contents/MacOS"
    mkdir -p "${KEXTS_DIR}/ArcBridgeCore.kext/Contents/MacOS"
    mkdir -p "${KEXTS_DIR}/ArcBridgeMetal.kext/Contents/MacOS"
}

# Function to check and install dependencies
install_dependencies() {
    log "Checking and installing dependencies" "STEP"
    
    # Check for Xcode Command Line Tools
    if ! xcode-select -p &>/dev/null; then
        log "Installing Xcode Command Line Tools" "INFO"
        xcode-select --install
        log "Please complete the Xcode Command Line Tools installation and run this script again" "WARNING"
        exit 1
    fi
    
    # Check for Homebrew
    if ! command -v brew &>/dev/null; then
        log "Installing Homebrew" "INFO"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    
    # Install required brew packages (lief removed – use pip instead)
    log "Installing required Homebrew packages" "INFO"
    if ! brew install cmake python@3.11 llvm; then
        log "Homebrew package installation failed" "ERROR"
        exit 1
    fi

    # Install LIEF via pip (more reliable than brew)
    log "Installing Python package: lief" "INFO"
    if ! pip3 install --upgrade lief --break-system-packages >/dev/null 2>&1; then
        log "WARN: Failed to install 'lief' with pip. Linux driver extraction will be skipped." "WARNING"
        LIEF_AVAILABLE=0
    else
        LIEF_AVAILABLE=1
    fi
    
    # Install Python packages
    log "Installing Python packages" "INFO"
    pip3 install requests tqdm pyelftools --break-system-packages
}

# Function to compile NVIDIA kexts
compile_nvidia_kexts() {
    log "Compiling NVIDIA kexts" "STEP"
    
    # Create build directory for NVIDIA kexts
    mkdir -p "${BUILD_DIR}/nvidia"
    cd "${BUILD_DIR}/nvidia"
    
    # Compile NVBridgeCore kext
    log "Compiling NVBridgeCore kext" "INFO"
    clang++ -std=c++17 -O2 -Wall -Wextra -fPIC -shared \
        -framework IOKit -framework CoreFoundation \
        -o "${KEXTS_DIR}/NVBridgeCore.kext/Contents/MacOS/NVBridgeCore" \
        "${SRC_DIR}/nvidia/nvbridge_core.cpp" \
        "${SRC_DIR}/nvidia/nvbridge_symbols.cpp"
    
    # Compile NVBridgeMetal kext
    log "Compiling NVBridgeMetal kext" "INFO"
    clang++ -std=c++17 -O2 -Wall -Wextra -fPIC -shared \
        -framework IOKit -framework CoreFoundation -framework Metal \
        -o "${KEXTS_DIR}/NVBridgeMetal.kext/Contents/MacOS/NVBridgeMetal" \
        "${SRC_DIR}/nvidia/nvbridge_metal.cpp"
    
    # Compile NVBridgeCUDA kext
    log "Compiling NVBridgeCUDA kext" "INFO"
    clang++ -std=c++17 -O2 -Wall -Wextra -fPIC -shared \
        -framework IOKit -framework CoreFoundation \
        -o "${KEXTS_DIR}/NVBridgeCUDA.kext/Contents/MacOS/NVBridgeCUDA" \
        "${SRC_DIR}/nvidia/nvbridge_cuda.cpp"
    
    # Create Info.plist files for NVIDIA kexts
    create_nvidia_info_plists
    
    log "NVIDIA kexts compiled successfully" "INFO"
}

# Function to compile Intel Arc kexts
compile_intel_arc_kexts() {
    log "Compiling Intel Arc kexts" "STEP"
    
    # Create build directory for Intel Arc kexts
    mkdir -p "${BUILD_DIR}/intel_arc"
    cd "${BUILD_DIR}/intel_arc"
    
    # Compile ArcBridgeCore kext
    log "Compiling ArcBridgeCore kext" "INFO"
    clang++ -std=c++17 -O2 -Wall -Wextra -fPIC -shared \
        -framework IOKit -framework CoreFoundation \
        -o "${KEXTS_DIR}/ArcBridgeCore.kext/Contents/MacOS/ArcBridgeCore" \
        "${SRC_DIR}/intel_arc/arc_bridge.cpp" \
        "${SRC_DIR}/intel_arc/arc_symbols.cpp"
    
    # Compile ArcBridgeMetal kext
    log "Compiling ArcBridgeMetal kext" "INFO"
    clang++ -std=c++17 -O2 -Wall -Wextra -fPIC -shared \
        -framework IOKit -framework CoreFoundation -framework Metal \
        -o "${KEXTS_DIR}/ArcBridgeMetal.kext/Contents/MacOS/ArcBridgeMetal" \
        "${SRC_DIR}/intel_arc/arc_bridge_metal.cpp"
    
    # Create Info.plist files for Intel Arc kexts
    create_intel_arc_info_plists
    
    log "Intel Arc kexts compiled successfully" "INFO"
}

# Function to create Info.plist files for NVIDIA kexts
create_nvidia_info_plists() {
    log "Creating Info.plist files for NVIDIA kexts" "INFO"
    
    # NVBridgeCore Info.plist
    cat > "${KEXTS_DIR}/NVBridgeCore.kext/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleExecutable</key>
    <string>NVBridgeCore</string>
    <key>CFBundleIdentifier</key>
    <string>${NVBRIDGE_BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>NVBridgeCore</string>
    <key>CFBundlePackageType</key>
    <string>KEXT</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>IOKitPersonalities</key>
    <dict>
        <key>NVBridgeCore</key>
        <dict>
            <key>CFBundleIdentifier</key>
            <string>${NVBRIDGE_BUNDLE_ID}</string>
            <key>IOClass</key>
            <string>NVBridgeCore</string>
            <key>IOMatchCategory</key>
            <string>NVBridgeCore</string>
            <key>IOPCIClassMatch</key>
            <string>0x03000000&amp;0xff000000</string>
            <key>IOPCIMatch</key>
            <string>0x13c210de 0x17c810de 0x1b8110de 0x1b0610de</string>
            <key>IOProviderClass</key>
            <string>IOPCIDevice</string>
        </dict>
    </dict>
    <key>OSBundleLibraries</key>
    <dict>
        <key>com.apple.iokit.IOPCIFamily</key>
        <string>2.9</string>
        <key>com.apple.kpi.bsd</key>
        <string>16.7</string>
        <key>com.apple.kpi.iokit</key>
        <string>16.7</string>
        <key>com.apple.kpi.libkern</key>
        <string>16.7</string>
        <key>com.apple.kpi.mach</key>
        <string>16.7</string>
    </dict>
</dict>
</plist>
EOF

    # NVBridgeMetal Info.plist
    cat > "${KEXTS_DIR}/NVBridgeMetal.kext/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleExecutable</key>
    <string>NVBridgeMetal</string>
    <key>CFBundleIdentifier</key>
    <string>${NVBRIDGE_METAL_BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>NVBridgeMetal</string>
    <key>CFBundlePackageType</key>
    <string>KEXT</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>IOKitPersonalities</key>
    <dict>
        <key>NVBridgeMetal</key>
        <dict>
            <key>CFBundleIdentifier</key>
            <string>${NVBRIDGE_METAL_BUNDLE_ID}</string>
            <key>IOClass</key>
            <string>NVBridgeMetal</string>
            <key>IOMatchCategory</key>
            <string>NVBridgeMetal</string>
            <key>IOPCIClassMatch</key>
            <string>0x03000000&amp;0xff000000</string>
            <key>IOPCIMatch</key>
            <string>0x13c210de 0x17c810de 0x1b8110de 0x1b0610de</string>
            <key>IOProviderClass</key>
            <string>IOPCIDevice</string>
        </dict>
    </dict>
    <key>OSBundleLibraries</key>
    <dict>
        <key>com.apple.iokit.IOPCIFamily</key>
        <string>2.9</string>
        <key>com.apple.kpi.bsd</key>
        <string>16.7</string>
        <key>com.apple.kpi.iokit</key>
        <string>16.7</string>
        <key>com.apple.kpi.libkern</key>
        <string>16.7</string>
        <key>com.apple.kpi.mach</key>
        <string>16.7</string>
        <key>${NVBRIDGE_BUNDLE_ID}</key>
        <string>${VERSION}</string>
    </dict>
</dict>
</plist>
EOF

    # NVBridgeCUDA Info.plist
    cat > "${KEXTS_DIR}/NVBridgeCUDA.kext/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleExecutable</key>
    <string>NVBridgeCUDA</string>
    <key>CFBundleIdentifier</key>
    <string>${NVBRIDGE_CUDA_BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>NVBridgeCUDA</string>
    <key>CFBundlePackageType</key>
    <string>KEXT</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>IOKitPersonalities</key>
    <dict>
        <key>NVBridgeCUDA</key>
        <dict>
            <key>CFBundleIdentifier</key>
            <string>${NVBRIDGE_CUDA_BUNDLE_ID}</string>
            <key>IOClass</key>
            <string>NVBridgeCUDA</string>
            <key>IOMatchCategory</key>
            <string>NVBridgeCUDA</string>
            <key>IOPCIClassMatch</key>
            <string>0x03000000&amp;0xff000000</string>
            <key>IOPCIMatch</key>
            <string>0x13c210de 0x17c810de 0x1b8110de 0x1b0610de</string>
            <key>IOProviderClass</key>
            <string>IOPCIDevice</string>
        </dict>
    </dict>
    <key>OSBundleLibraries</key>
    <dict>
        <key>com.apple.iokit.IOPCIFamily</key>
        <string>2.9</string>
        <key>com.apple.kpi.bsd</key>
        <string>16.7</string>
        <key>com.apple.kpi.iokit</key>
        <string>16.7</string>
        <key>com.apple.kpi.libkern</key>
        <string>16.7</string>
        <key>com.apple.kpi.mach</key>
        <string>16.7</string>
        <key>${NVBRIDGE_BUNDLE_ID}</key>
        <string>${VERSION}</string>
    </dict>
</dict>
</plist>
EOF
}

# Function to create Info.plist files for Intel Arc kexts
create_intel_arc_info_plists() {
    log "Creating Info.plist files for Intel Arc kexts" "INFO"
    
    # ArcBridgeCore Info.plist
    cat > "${KEXTS_DIR}/ArcBridgeCore.kext/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleExecutable</key>
    <string>ArcBridgeCore</string>
    <key>CFBundleIdentifier</key>
    <string>${ARCBRIDGE_BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>ArcBridgeCore</string>
    <key>CFBundlePackageType</key>
    <string>KEXT</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>IOKitPersonalities</key>
    <dict>
        <key>ArcBridgeCore</key>
        <dict>
            <key>CFBundleIdentifier</key>
            <string>${ARCBRIDGE_BUNDLE_ID}</string>
            <key>IOClass</key>
            <string>ArcBridgeCore</string>
            <key>IOMatchCategory</key>
            <string>ArcBridgeCore</string>
            <key>IOPCIClassMatch</key>
            <string>0x03000000&amp;0xff000000</string>
            <key>IOPCIMatch</key>
            <string>0x56a08086 0x56a18086 0x56a58086 0x56a68086</string>
            <key>IOProviderClass</key>
            <string>IOPCIDevice</string>
        </dict>
    </dict>
    <key>OSBundleLibraries</key>
    <dict>
        <key>com.apple.iokit.IOPCIFamily</key>
        <string>2.9</string>
        <key>com.apple.kpi.bsd</key>
        <string>16.7</string>
        <key>com.apple.kpi.iokit</key>
        <string>16.7</string>
        <key>com.apple.kpi.libkern</key>
        <string>16.7</string>
        <key>com.apple.kpi.mach</key>
        <string>16.7</string>
    </dict>
</dict>
</plist>
EOF

    # ArcBridgeMetal Info.plist
    cat > "${KEXTS_DIR}/ArcBridgeMetal.kext/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleExecutable</key>
    <string>ArcBridgeMetal</string>
    <key>CFBundleIdentifier</key>
    <string>${ARCBRIDGE_METAL_BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>ArcBridgeMetal</string>
    <key>CFBundlePackageType</key>
    <string>KEXT</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>IOKitPersonalities</key>
    <dict>
        <key>ArcBridgeMetal</key>
        <dict>
            <key>CFBundleIdentifier</key>
            <string>${ARCBRIDGE_METAL_BUNDLE_ID}</string>
            <key>IOClass</key>
            <string>ArcBridgeMetal</string>
            <key>IOMatchCategory</key>
            <string>ArcBridgeMetal</string>
            <key>IOPCIClassMatch</key>
            <string>0x03000000&amp;0xff000000</string>
            <key>IOPCIMatch</key>
            <string>0x56a08086 0x56a18086 0x56a58086 0x56a68086</string>
            <key>IOProviderClass</key>
            <string>IOPCIDevice</string>
        </dict>
    </dict>
    <key>OSBundleLibraries</key>
    <dict>
        <key>com.apple.iokit.IOPCIFamily</key>
        <string>2.9</string>
        <key>com.apple.kpi.bsd</key>
        <string>16.7</string>
        <key>com.apple.kpi.iokit</key>
        <string>16.7</string>
        <key>com.apple.kpi.libkern</key>
        <string>16.7</string>
        <key>com.apple.kpi.mach</key>
        <string>16.7</string>
        <key>${ARCBRIDGE_BUNDLE_ID}</key>
        <string>${VERSION}</string>
    </dict>
</dict>
</plist>
EOF
}

# Function to build Python components
build_python_components() {
    log "Building Python components" "STEP"
    
    # Create Python package structure
    mkdir -p "${BUILD_DIR}/python/skyscope"
    
    # Copy Python files
    cp "${SCRIPT_DIR}/skyscope_enhanced.py" "${BUILD_DIR}/python/skyscope/"
    cp -r "${SRC_DIR}/installers" "${BUILD_DIR}/python/skyscope/"
    cp -r "${SRC_DIR}/utils" "${BUILD_DIR}/python/skyscope/"
    
    # Create __init__.py
    touch "${BUILD_DIR}/python/skyscope/__init__.py"
    touch "${BUILD_DIR}/python/skyscope/installers/__init__.py"
    touch "${BUILD_DIR}/python/skyscope/utils/__init__.py"
    
    # Create setup.py
    cat > "${BUILD_DIR}/python/setup.py" << EOF
from setuptools import setup, find_packages

setup(
    name="skyscope",
    version="${VERSION}",
    packages=find_packages(),
    install_requires=[
        "requests",
        "tqdm",
        "pyelftools",
    ],
    entry_points={
        "console_scripts": [
            "skyscope=skyscope.skyscope_enhanced:main",
        ],
    },
    author="Miss Casey Jay Topojani",
    author_email="info@skyscope.ai",
    description="Skyscope macOS Patcher for NVIDIA and Intel Arc support",
)
EOF
    
    # Install Python package
    cd "${BUILD_DIR}/python"
    pip3 install -e . --break-system-packages
    
    log "Python components built successfully" "INFO"
}

# Function to extract Linux drivers
extract_linux_drivers() {
    # Skip extraction when lief is not present
    if [[ "${LIEF_AVAILABLE}" == "0" ]]; then
        log "Skipping Linux driver extraction – lief not available." "WARNING"
        return 0
    fi

    log "Extracting Linux drivers" "STEP"
    
    # Create directories
    mkdir -p "${BUILD_DIR}/drivers/nvidia"
    mkdir -p "${BUILD_DIR}/drivers/intel"
    
    # Run extractor for NVIDIA drivers
    log "Extracting NVIDIA drivers" "INFO"
    python3 "${SRC_DIR}/utils/linux_extractor.py" --vendor nvidia --work-dir "${BUILD_DIR}/drivers"
    
    # Run extractor for Intel drivers
    log "Extracting Intel drivers" "INFO"
    python3 "${SRC_DIR}/utils/linux_extractor.py" --vendor intel --work-dir "${BUILD_DIR}/drivers"
    
    log "Linux drivers extracted successfully" "INFO"
}

# Function to install kexts
install_kexts() {
    log "Installing kexts" "STEP"

    # Honor --no-kexts flag
    if [[ "${SKIP_KEXTS}" == "1" ]]; then
        log "Kext installation skipped per user request." "INFO"
        return 0
    fi
    
    # Check if kextcache is available
    if ! command -v kextcache &>/dev/null; then
        log "kextcache command not found. Cannot install kexts." "ERROR"
        return 1
    fi

    # Ensure we have sudo rights for the upcoming filesystem operations
    prompt_for_sudo
    
    # Install NVIDIA kexts
    log "Installing NVIDIA kexts" "INFO"
    sudo cp -r "${KEXTS_DIR}/NVBridgeCore.kext" "/Library/Extensions/"
    sudo cp -r "${KEXTS_DIR}/NVBridgeMetal.kext" "/Library/Extensions/"
    sudo cp -r "${KEXTS_DIR}/NVBridgeCUDA.kext" "/Library/Extensions/"
    
    # Install Intel Arc kexts
    log "Installing Intel Arc kexts" "INFO"
    sudo cp -r "${KEXTS_DIR}/ArcBridgeCore.kext" "/Library/Extensions/"
    sudo cp -r "${KEXTS_DIR}/ArcBridgeMetal.kext" "/Library/Extensions/"
    
    # Set permissions
    log "Setting kext permissions" "INFO"
    sudo chmod -R 755 "/Library/Extensions/NVBridgeCore.kext"
    sudo chmod -R 755 "/Library/Extensions/NVBridgeMetal.kext"
    sudo chmod -R 755 "/Library/Extensions/NVBridgeCUDA.kext"
    sudo chmod -R 755 "/Library/Extensions/ArcBridgeCore.kext"
    sudo chmod -R 755 "/Library/Extensions/ArcBridgeMetal.kext"
    
    sudo chown -R root:wheel "/Library/Extensions/NVBridgeCore.kext"
    sudo chown -R root:wheel "/Library/Extensions/NVBridgeMetal.kext"
    sudo chown -R root:wheel "/Library/Extensions/NVBridgeCUDA.kext"
    sudo chown -R root:wheel "/Library/Extensions/ArcBridgeCore.kext"
    sudo chown -R root:wheel "/Library/Extensions/ArcBridgeMetal.kext"
    
    # Update kext cache
    log "Updating kext cache" "INFO"
    sudo kextcache -i /
    
    log "Kexts installed successfully" "INFO"
}

# Function to apply boot arguments
apply_boot_arguments() {
    log "Applying boot arguments" "STEP"
    
    # nvram requires root privileges
    prompt_for_sudo

    # Set boot arguments for NVIDIA and Intel Arc
    log "Setting boot arguments" "INFO"
    sudo nvram boot-args="ngfxcompat=1 ngfxgl=1 nvda_drv_vrl=1 iarccompat=1 iarcgl=1 -v"
    
    log "Boot arguments applied successfully" "INFO"
}

# Function to create bootable USB installer
create_bootable_installer() {
    log "Creating bootable USB installer" "STEP"
    
    # Check if we have a USB device
    if [ -z "$1" ]; then
        log "No USB device specified" "ERROR"
        return 1
    fi
    
    USB_DEVICE="$1"
    
    # Check if the device exists
    if [ ! -b "$USB_DEVICE" ]; then
        log "USB device $USB_DEVICE does not exist" "ERROR"
        return 1
    fi
    
    # Run the USB creator script
    log "Running USB creator script" "INFO"
    python3 "${SRC_DIR}/installers/usb_creator.py" --disk "$USB_DEVICE" --hardware nvidia_gtx970 intel_arc770
    
    log "Bootable USB installer created successfully" "INFO"
}

# Function to perform cleanup
cleanup() {
    log "Cleaning up temporary files" "STEP"
    
    # Remove temporary directory
    rm -rf "${TEMP_DIR}"
    
    log "Cleanup complete" "INFO"
}

# Function to show completion message
show_completion() {
    echo -e "${GREEN}${BOLD}"
    echo "=============================================================================="
    echo "             Skyscope macOS Patcher Installation Complete!                    "
    echo "=============================================================================="
    echo -e "${RESET}"
    echo "The Skyscope macOS Patcher has been successfully built and installed."
    echo ""
    echo "NVIDIA and Intel Arc support has been enabled for macOS Sequoia and Tahoe."
    echo ""
    echo "Please restart your computer for the changes to take effect."
    echo ""
    echo -e "${YELLOW}Note: You may need to disable System Integrity Protection (SIP)${RESET}"
    echo "to fully utilize the NVIDIA and Intel Arc drivers."
    echo ""
    echo "To disable SIP, boot into Recovery Mode (Command+R during startup)"
    echo "and run the following command in Terminal:"
    echo -e "${CYAN}csrutil disable${RESET}"
    echo ""
    echo "Thank you for using Skyscope macOS Patcher!"
}

# Main function
main() {
    # Initialize log file
    echo "Skyscope macOS Patcher Build Log - $(date)" > "${LOG_FILE}"
    
    # Show banner
    show_banner
    
    # Ensure script is NOT run as root for Homebrew safety
    check_not_root
    
    # Create directories
    create_directories
    
    # Install dependencies
    install_dependencies
    
    # Extract Linux drivers
    extract_linux_drivers
    
    # Compile NVIDIA kexts
    compile_nvidia_kexts
    
    # Compile Intel Arc kexts
    compile_intel_arc_kexts
    
    # Build Python components
    build_python_components
    
    # Install kexts
    install_kexts
    
    # Apply boot arguments
    apply_boot_arguments
    
    # Cleanup
    cleanup
    
    # Show completion message
    show_completion
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --usb)
            USB_DEVICE="$2"
            shift 2
            ;;
        --no-kexts)
            SKIP_KEXTS=1
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --usb DEVICE    Create bootable USB installer on the specified device"
            echo "  --no-kexts      Skip kext installation"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Run main function
main

# Create bootable USB installer if specified
if [ -n "$USB_DEVICE" ]; then
    create_bootable_installer "$USB_DEVICE"
fi

exit 0
