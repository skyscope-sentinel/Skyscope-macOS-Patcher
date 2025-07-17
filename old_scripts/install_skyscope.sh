#!/bin/bash
#
# install_skyscope.sh
# Skyscope macOS Patcher Installation Script
#
# Developer: Miss Casey Jay Topojani
# Version: 1.0.0
# Date: July 9, 2025
#
# This script handles downloading dependencies, setting up the environment,
# and installing the Skyscope macOS Patcher application.

# Exit on error
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/build"
RESOURCES_DIR="${SCRIPT_DIR}/resources"
PAYLOADS_DIR="${SCRIPT_DIR}/payloads"
LOGS_DIR="${SCRIPT_DIR}/logs"
TEMP_DIR="${WORK_DIR}/temp"

OPENCORE_VERSION="1.0.5"
OPENCORE_REPO="https://github.com/acidanthera/OpenCorePkg"
OPENCORE_DIR="${PAYLOADS_DIR}/OpenCorePkg"

KEXTS_DIR="${PAYLOADS_DIR}/Kexts"
NVIDIA_DIR="${PAYLOADS_DIR}/NVIDIA"
CUDA_DIR="${NVIDIA_DIR}/cuda"

LOG_FILE="${LOGS_DIR}/install_$(date +%Y%m%d_%H%M%S).log"

# Required tools
REQUIRED_TOOLS=(
    "git"
    "curl"
    "python3"
    "pip3"
    "xcodebuild"
    "nasm"
    "mtoc"
    "dmgbuild"
    "create-dmg"
)

# Kexts to download
KEXTS=(
    "https://github.com/acidanthera/Lilu/releases/download/1.7.1/Lilu-1.7.1-RELEASE.zip"
    "https://github.com/acidanthera/WhateverGreen/releases/download/1.7.0/WhateverGreen-1.7.0-RELEASE.zip"
    "https://github.com/acidanthera/VirtualSMC/releases/download/1.3.7/VirtualSMC-1.3.7-RELEASE.zip"
    "https://github.com/acidanthera/AppleALC/releases/download/1.9.5/AppleALC-1.9.5-RELEASE.zip"
    "https://github.com/acidanthera/CPUFriend/releases/download/1.3.0/CPUFriend-1.3.0-RELEASE.zip"
    "https://github.com/acidanthera/NVMeFix/releases/download/1.1.3/NVMeFix-1.1.3-RELEASE.zip"
    "https://github.com/acidanthera/RestrictEvents/releases/download/1.1.6/RestrictEvents-1.1.6-RELEASE.zip"
    "https://github.com/usr-sse2/CpuTopologyRebuild/releases/download/2.0.2/CpuTopologyRebuild-2.0.2-RELEASE.zip"
    "https://github.com/Mieze/RTL8111_driver_for_OS_X/releases/download/v2.4.2/RealtekRTL8111-V2.4.2.zip"
)

# Function to log messages
log() {
    local level="$1"
    local message="$2"
    local color=""
    
    case "${level}" in
        "INFO")
            color="${GREEN}"
            ;;
        "WARNING")
            color="${YELLOW}"
            ;;
        "ERROR")
            color="${RED}"
            ;;
        "DEBUG")
            color="${CYAN}"
            ;;
        *)
            color="${NC}"
            ;;
    esac
    
    # Log to console
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] ${message}${NC}"
    
    # Log to file
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] ${message}" >> "${LOG_FILE}"
}

# Function to check for required tools
check_requirements() {
    log "INFO" "Checking for required tools..."
    
    local missing_tools=()
    
    for tool in "${REQUIRED_TOOLS[@]}"; do
        if ! command -v "${tool}" &> /dev/null; then
            missing_tools+=("${tool}")
        fi
    done
    
    if [ ${#missing_tools[@]} -gt 0 ]; then
        log "ERROR" "The following required tools are missing: ${missing_tools[*]}"
        log "INFO" "Please install the missing tools and try again."
        
        if [[ "$OSTYPE" == "darwin"* ]]; then
            log "INFO" "You can install most tools using Homebrew: brew install ${missing_tools[*]}"
            log "INFO" "For mtoc, you need to install Xcode Command Line Tools: xcode-select --install"
        fi
        
        exit 1
    fi
    
    log "INFO" "All required tools are available."
}

# Function to create directories
create_directories() {
    log "INFO" "Creating directories..."
    
    mkdir -p "${WORK_DIR}"
    mkdir -p "${RESOURCES_DIR}"
    mkdir -p "${PAYLOADS_DIR}"
    mkdir -p "${LOGS_DIR}"
    mkdir -p "${TEMP_DIR}"
    mkdir -p "${KEXTS_DIR}"
    mkdir -p "${NVIDIA_DIR}"
    mkdir -p "${CUDA_DIR}"
    
    log "INFO" "Directories created successfully."
}

# Function to download and setup OpenCore
download_opencore() {
    log "INFO" "Downloading OpenCore ${OPENCORE_VERSION}..."
    
    if [ -d "${OPENCORE_DIR}" ]; then
        log "INFO" "OpenCore directory exists. Updating..."
        cd "${OPENCORE_DIR}"
        git fetch --all
        git checkout "tags/${OPENCORE_VERSION}" -b "build-${OPENCORE_VERSION}"
    else
        log "INFO" "Cloning OpenCore repository..."
        git clone "${OPENCORE_REPO}" "${OPENCORE_DIR}"
        cd "${OPENCORE_DIR}"
        git checkout "tags/${OPENCORE_VERSION}" -b "build-${OPENCORE_VERSION}"
    fi
    
    log "INFO" "OpenCore setup complete."
}

# Function to build OpenCore
build_opencore() {
    log "INFO" "Building OpenCore ${OPENCORE_VERSION}..."
    
    cd "${OPENCORE_DIR}"
    
    # Check if build script exists
    if [ ! -f "./build_oc.tool" ]; then
        log "ERROR" "OpenCore build script not found."
        exit 1
    fi
    
    # Build OpenCore
    log "INFO" "Running OpenCore build script..."
    chmod +x ./build_oc.tool
    ./build_oc.tool || {
        log "ERROR" "Failed to build OpenCore."
        exit 1
    }
    
    log "INFO" "OpenCore built successfully."
}

# Function to download kexts
download_kexts() {
    log "INFO" "Downloading kexts..."
    
    cd "${TEMP_DIR}"
    
    for kext_url in "${KEXTS[@]}"; do
        kext_filename=$(basename "${kext_url}")
        log "INFO" "Downloading ${kext_filename}..."
        
        curl -L -o "${kext_filename}" "${kext_url}" || {
            log "ERROR" "Failed to download ${kext_filename}."
            continue
        }
        
        # Extract kext
        unzip -o "${kext_filename}" -d "${KEXTS_DIR}" > /dev/null || {
            log "ERROR" "Failed to extract ${kext_filename}."
            continue
        }
        
        log "INFO" "${kext_filename} downloaded and extracted successfully."
    done
    
    log "INFO" "All kexts downloaded successfully."
}

# Function to create custom NVBridge kext
create_nvbridge_kext() {
    log "INFO" "Creating Skyscope-NVBridge.kext..."
    
    NVBRIDGE_DIR="${NVIDIA_DIR}/Skyscope-NVBridge.kext"
    NVBRIDGE_CONTENTS="${NVBRIDGE_DIR}/Contents"
    NVBRIDGE_MACOS="${NVBRIDGE_CONTENTS}/MacOS"
    NVBRIDGE_RESOURCES="${NVBRIDGE_CONTENTS}/Resources"
    
    mkdir -p "${NVBRIDGE_MACOS}"
    mkdir -p "${NVBRIDGE_RESOURCES}"
    
    # Create Info.plist
    cat > "${NVBRIDGE_CONTENTS}/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>BuildMachineOSBuild</key>
    <string>23G91</string>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleExecutable</key>
    <string>Skyscope-NVBridge</string>
    <key>CFBundleIdentifier</key>
    <string>io.skyscope.NVBridge</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Skyscope-NVBridge</string>
    <key>CFBundlePackageType</key>
    <string>KEXT</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleSupportedPlatforms</key>
    <array>
        <string>MacOSX</string>
    </array>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>DTCompiler</key>
    <string>com.apple.compilers.llvm.clang.1_0</string>
    <key>DTPlatformBuild</key>
    <string>14C18</string>
    <key>DTPlatformName</key>
    <string>macosx</string>
    <key>DTPlatformVersion</key>
    <string>13.5</string>
    <key>DTSDKBuild</key>
    <string>22G62</string>
    <key>DTSDKName</key>
    <string>macosx13.5</string>
    <key>DTXcode</key>
    <string>1430</string>
    <key>DTXcodeBuild</key>
    <string>14E222b</string>
    <key>IOKitPersonalities</key>
    <dict>
        <key>NVBridgeDriver</key>
        <dict>
            <key>CFBundleIdentifier</key>
            <string>io.skyscope.NVBridge</string>
            <key>IOClass</key>
            <string>NVBridgeDriver</string>
            <key>IOMatchCategory</key>
            <string>NVBridgeDriver</string>
            <key>IOPCIClassMatch</key>
            <string>0x03000000&amp;0xff000000</string>
            <key>IOPCIMatch</key>
            <string>0x0000de10&amp;0x0000ffff</string>
            <key>IOProbeScore</key>
            <integer>60000</integer>
            <key>IOProviderClass</key>
            <string>IOPCIDevice</string>
        </dict>
    </dict>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2025 Miss Casey Jay Topojani. All rights reserved.</string>
    <key>OSBundleLibraries</key>
    <dict>
        <key>com.apple.iokit.IOPCIFamily</key>
        <string>2.9</string>
        <key>com.apple.kpi.bsd</key>
        <string>20.0.0</string>
        <key>com.apple.kpi.dsep</key>
        <string>20.0.0</string>
        <key>com.apple.kpi.iokit</key>
        <string>20.0.0</string>
        <key>com.apple.kpi.libkern</key>
        <string>20.0.0</string>
        <key>com.apple.kpi.mach</key>
        <string>20.0.0</string>
        <key>com.apple.kpi.unsupported</key>
        <string>20.0.0</string>
        <key>org.lilu.kext</key>
        <string>1.6.0</string>
    </dict>
    <key>OSBundleRequired</key>
    <string>Root</string>
</dict>
</plist>
EOF

    # Create placeholder executable
    echo '#!/bin/sh
echo "Skyscope-NVBridge placeholder"
exit 0' > "${NVBRIDGE_MACOS}/Skyscope-NVBridge"
    chmod +x "${NVBRIDGE_MACOS}/Skyscope-NVBridge"
    
    log "INFO" "Skyscope-NVBridge.kext created successfully."
}

# Function to download NVIDIA CUDA drivers
download_nvidia_cuda() {
    log "INFO" "Downloading NVIDIA CUDA drivers..."
    
    cd "${TEMP_DIR}"
    
    CUDA_URL="https://developer.download.nvidia.com/compute/cuda/12.9.1/local_installers/cuda-repo-debian12-12-9-local_12.9.1-575.57.08-1_amd64.deb"
    CUDA_DEB="cuda-repo-debian12-12-9-local_12.9.1-575.57.08-1_amd64.deb"
    
    log "INFO" "Downloading CUDA package..."
    curl -L -o "${CUDA_DEB}" "${CUDA_URL}" || {
        log "ERROR" "Failed to download CUDA package."
        return 1
    }
    
    log "INFO" "Extracting CUDA package..."
    mkdir -p "${TEMP_DIR}/cuda_extract"
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # On macOS, use ar to extract the deb
        cd "${TEMP_DIR}/cuda_extract"
        ar x "../${CUDA_DEB}" || {
            log "ERROR" "Failed to extract CUDA deb package."
            return 1
        }
        
        # Extract data.tar.xz
        tar -xf data.tar.xz || {
            log "ERROR" "Failed to extract data.tar.xz."
            return 1
        }
    else
        # On Linux, use dpkg-deb
        dpkg-deb -x "${CUDA_DEB}" "${TEMP_DIR}/cuda_extract" || {
            log "ERROR" "Failed to extract CUDA deb package."
            return 1
        }
    fi
    
    # Copy CUDA files to CUDA_DIR
    log "INFO" "Copying CUDA files..."
    mkdir -p "${CUDA_DIR}"
    
    # Find and copy CUDA libraries
    find "${TEMP_DIR}/cuda_extract" -name "*.so*" -exec cp {} "${CUDA_DIR}/" \;
    find "${TEMP_DIR}/cuda_extract" -name "*.a" -exec cp {} "${CUDA_DIR}/" \;
    
    log "INFO" "CUDA drivers downloaded and extracted successfully."
}

# Function to setup Python environment
setup_python_env() {
    log "INFO" "Setting up Python environment..."
    
    # Create virtual environment
    python3 -m venv "${WORK_DIR}/venv" || {
        log "ERROR" "Failed to create Python virtual environment."
        exit 1
    }
    
    # Activate virtual environment
    source "${WORK_DIR}/venv/bin/activate" || {
        log "ERROR" "Failed to activate Python virtual environment."
        exit 1
    }
    
    # Install required Python packages
    log "INFO" "Installing Python packages..."
    pip3 install --upgrade pip
    pip3 install poetry
    pip3 install wxPython
    pip3 install pyobjc
    pip3 install pyinstaller
    pip3 install dmgbuild
    
    # Install project dependencies
    cd "${SCRIPT_DIR}"
    if [ -f "pyproject.toml" ]; then
        poetry install || {
            log "ERROR" "Failed to install project dependencies with Poetry."
            exit 1
        }
    elif [ -f "requirements.txt" ]; then
        pip3 install -r requirements.txt || {
            log "ERROR" "Failed to install project dependencies from requirements.txt."
            exit 1
        }
    else
        log "WARNING" "No pyproject.toml or requirements.txt found. Skipping dependency installation."
    fi
    
    log "INFO" "Python environment setup complete."
}

# Function to build the application
build_app() {
    log "INFO" "Building Skyscope macOS Patcher application..."
    
    cd "${SCRIPT_DIR}"
    
    # Activate virtual environment if not already activated
    if [ -z "${VIRTUAL_ENV}" ]; then
        source "${WORK_DIR}/venv/bin/activate" || {
            log "ERROR" "Failed to activate Python virtual environment."
            exit 1
        }
    fi
    
    # Build the app using PyInstaller
    log "INFO" "Running PyInstaller..."
    pyinstaller --clean --windowed \
                --name "Skyscope macOS Patcher" \
                --icon "${RESOURCES_DIR}/skyscope.icns" \
                --add-data "${RESOURCES_DIR}:resources" \
                --add-data "${PAYLOADS_DIR}:payloads" \
                --osx-bundle-identifier "io.skyscope.patcher" \
                --hidden-import "wx" \
                --hidden-import "wx.adv" \
                --hidden-import "wx.lib.agw.gradientbutton" \
                --hidden-import "wx.lib.agw.aui" \
                "${SCRIPT_DIR}/skyscope_patcher.py" || {
        log "ERROR" "Failed to build application with PyInstaller."
        exit 1
    }
    
    log "INFO" "Application built successfully."
}

# Function to create DMG installer
create_dmg() {
    log "INFO" "Creating DMG installer..."
    
    APP_PATH="${SCRIPT_DIR}/dist/Skyscope macOS Patcher.app"
    DMG_PATH="${SCRIPT_DIR}/dist/Skyscope_macOS_Patcher_v1.0.0.dmg"
    
    if [ ! -d "${APP_PATH}" ]; then
        log "ERROR" "Application not found at ${APP_PATH}"
        exit 1
    fi
    
    # Create DMG
    create-dmg \
        --volname "Skyscope macOS Patcher" \
        --volicon "${RESOURCES_DIR}/skyscope.icns" \
        --window-pos 200 120 \
        --window-size 800 400 \
        --icon-size 100 \
        --icon "Skyscope macOS Patcher.app" 200 190 \
        --hide-extension "Skyscope macOS Patcher.app" \
        --app-drop-link 600 185 \
        "${DMG_PATH}" \
        "${APP_PATH}" || {
        log "ERROR" "Failed to create DMG installer."
        exit 1
    }
    
    log "INFO" "DMG installer created successfully at ${DMG_PATH}"
}

# Function to clean up
cleanup() {
    log "INFO" "Cleaning up temporary files..."
    
    # Remove temporary directory
    rm -rf "${TEMP_DIR}"
    
    log "INFO" "Cleanup complete."
}

# Main function
main() {
    log "INFO" "Starting Skyscope macOS Patcher installation..."
    
    # Check if running as root
    if [ "$(id -u)" -eq 0 ]; then
        log "WARNING" "This script is running as root. This is not recommended."
    fi
    
    # Check requirements
    check_requirements
    
    # Create directories
    create_directories
    
    # Download and build OpenCore
    download_opencore
    build_opencore
    
    # Download kexts
    download_kexts
    
    # Create NVBridge kext
    create_nvbridge_kext
    
    # Download NVIDIA CUDA drivers
    download_nvidia_cuda
    
    # Setup Python environment
    setup_python_env
    
    # Build the application
    build_app
    
    # Create DMG installer
    create_dmg
    
    # Clean up
    cleanup
    
    log "INFO" "Skyscope macOS Patcher installation completed successfully!"
    log "INFO" "You can find the application at: ${SCRIPT_DIR}/dist/Skyscope macOS Patcher.app"
    log "INFO" "You can find the DMG installer at: ${SCRIPT_DIR}/dist/Skyscope_macOS_Patcher_v1.0.0.dmg"
}

# Run main function
main "$@"
