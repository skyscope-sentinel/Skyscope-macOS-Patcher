#!/bin/bash
#
# simple_build.sh
# Simplified Build Script for Skyscope Sentinel Intelligence Patcher
#
# This script builds a customized version of OpenCore Legacy Patcher with
# Skyscope branding and enhanced GPU support.
#
# Copyright (c) 2025 Skyscope Sentinel Intelligence
# Developer: Casey Jay Topojani
#

# Exit on error
set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$HOME/skyscope_build.log"
TEMP_DIR="$SCRIPT_DIR/temp"
OUTPUT_DIR="$SCRIPT_DIR/output"
OCLP_DIR="$TEMP_DIR/OpenCore-Legacy-Patcher"
OCLP_REPO="https://github.com/dortania/OpenCore-Legacy-Patcher.git"
APP_NAME="Skyscope Sentinel Intelligence Patcher"
APP_VERSION="1.0.0"
DEVELOPER_NAME="Casey Jay Topojani"
COMPANY_NAME="Skyscope Sentinel Intelligence"

# Function to log messages
log() {
    echo -e "${GREEN}[INFO]${NC} $1"
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] [INFO] $1" >> "$LOG_FILE"
}

# Function to log warnings
warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] [WARNING] $1" >> "$LOG_FILE"
}

# Function to log errors
error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] [ERROR] $1" >> "$LOG_FILE"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    error "This script should not be run as root (with sudo)"
    echo "Please run it as a normal user. The script will prompt for sudo when needed."
    exit 1
fi

# Create required directories
mkdir -p "$TEMP_DIR"
mkdir -p "$OUTPUT_DIR"

# Check Python version
log "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    error "Python 3 is not installed"
    echo "Please install Python 3.8 or newer"
    exit 1
fi

# Install dependencies
log "Installing dependencies..."

# Check for conda environment
if command -v conda &> /dev/null; then
    log "Conda detected, using conda to install dependencies"
    conda install -y -c conda-forge wxpython || warn "Failed to install wxPython via conda"
    python3 -m pip install pyinstaller packaging pillow || warn "Failed to install some pip packages"
else
    log "Using pip to install dependencies"
    python3 -m pip install wxpython || warn "Failed to install wxPython via pip"
    python3 -m pip install pyinstaller packaging pillow || warn "Failed to install some pip packages"
fi

# Clone or update OCLP repository
log "Getting OpenCore Legacy Patcher source code..."
if [ -d "$OCLP_DIR" ]; then
    log "Updating existing OCLP repository"
    cd "$OCLP_DIR"
    git pull
    cd "$SCRIPT_DIR"
else
    log "Cloning OCLP repository"
    git clone "$OCLP_REPO" "$OCLP_DIR"
fi

# Patch OCLP for Skyscope branding
log "Patching OCLP for Skyscope branding..."

# Backup constants.py
if [ -f "$OCLP_DIR/resources/constants.py" ]; then
    cp "$OCLP_DIR/resources/constants.py" "$TEMP_DIR/constants.py.backup"
    
    # Update branding in constants.py
    log "Updating branding in constants.py"
    sed -i.bak "s/self.patcher_version:.*str = \".*\"/self.patcher_version:                 str = \"$APP_VERSION\"/" "$OCLP_DIR/resources/constants.py"
    sed -i.bak "s/self.copyright_date:.*str = \".*\"/self.copyright_date:                  str = \"Copyright © 2025 $COMPANY_NAME\"/" "$OCLP_DIR/resources/constants.py"
    sed -i.bak "s/self.patcher_name:.*str = \".*\"/self.patcher_name:                    str = \"$APP_NAME\"/" "$OCLP_DIR/resources/constants.py"
    
    # Add developer name
    if ! grep -q "developer_name" "$OCLP_DIR/resources/constants.py"; then
        sed -i.bak "/self.patcher_name:/a\\        self.developer_name:                str = \"$DEVELOPER_NAME\"" "$OCLP_DIR/resources/constants.py"
    fi
else
    error "constants.py not found in OCLP repository"
    exit 1
fi

# Add macOS 26.x support to os_probe.py
if [ -f "$OCLP_DIR/resources/detections/os_probe.py" ]; then
    cp "$OCLP_DIR/resources/detections/os_probe.py" "$TEMP_DIR/os_probe.py.backup"
    
    log "Adding macOS 26.x support to os_probe.py"
    
    # Add Sequoia and Tahoe support
    if grep -q "def detect_os_version" "$OCLP_DIR/resources/detections/os_probe.py"; then
        sed -i.bak '/elif kernel_major == 23:/a\        elif kernel_major == 24:\n            return "Sequoia"\n        elif kernel_major == 25:\n            return "Tahoe"\n        elif kernel_major == 26:\n            return "Sequoia+"' "$OCLP_DIR/resources/detections/os_probe.py"
    fi
else
    warn "os_probe.py not found, skipping macOS 26.x support"
fi

# Build the application
log "Building the application..."

# Create build directory in OCLP
cd "$OCLP_DIR"

# Install required Python packages for build
python3 -m pip install pyinstaller || warn "Failed to install PyInstaller"

# Create simple PyInstaller spec file
cat > "$OCLP_DIR/skyscope.spec" << EOF
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['OpenCore-Patcher-GUI.command'],
    pathex=['$OCLP_DIR'],
    binaries=[],
    datas=[
        ('payloads', 'payloads'),
        ('resources', 'resources')
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='$APP_NAME',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/OC_Patcher.icns'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='$APP_NAME',
)

app = BUNDLE(
    coll,
    name='$APP_NAME.app',
    icon='resources/OC_Patcher.icns',
    bundle_identifier='com.skyscope.sentinel.patcher',
    info_plist={
        'CFBundleShortVersionString': '$APP_VERSION',
        'CFBundleVersion': '$APP_VERSION',
        'NSHumanReadableCopyright': 'Copyright © 2025 $COMPANY_NAME'
    }
)
EOF

# Run PyInstaller
log "Running PyInstaller..."
python3 -m PyInstaller --clean skyscope.spec

# Copy output to destination
if [ -d "$OCLP_DIR/dist/$APP_NAME.app" ]; then
    log "Copying application to output directory..."
    cp -R "$OCLP_DIR/dist/$APP_NAME.app" "$OUTPUT_DIR/"
    log "Build completed successfully!"
    echo -e "${GREEN}Application built successfully:${NC} $OUTPUT_DIR/$APP_NAME.app"
else
    error "Build failed, application not found"
    exit 1
fi

# Function to install the application
install_app() {
    log "Installing application to /Applications..."
    
    if [ ! -d "$OUTPUT_DIR/$APP_NAME.app" ]; then
        error "Application not found. Please build it first."
        exit 1
    fi
    
    # Request sudo privileges
    echo "Administrator privileges needed for installation"
    sudo cp -R "$OUTPUT_DIR/$APP_NAME.app" "/Applications/"
    
    if [ $? -eq 0 ]; then
        log "Installation completed successfully!"
        echo -e "${GREEN}Application installed to:${NC} /Applications/$APP_NAME.app"
    else
        error "Installation failed"
        exit 1
    fi
}

# Function to clean build artifacts
clean_build() {
    log "Cleaning build artifacts..."
    rm -rf "$TEMP_DIR"
    rm -rf "$OCLP_DIR/build"
    rm -rf "$OCLP_DIR/dist"
    log "Build artifacts cleaned successfully!"
}

# Process command line arguments
if [ "$1" == "--install" ]; then
    install_app
elif [ "$1" == "--clean" ]; then
    clean_build
elif [ "$1" == "--help" ]; then
    echo "Usage: $0 [OPTION]"
    echo "Options:"
    echo "  --install    Install the application to /Applications"
    echo "  --clean      Clean build artifacts"
    echo "  --help       Display this help message"
    echo "  (no option)  Build the application"
fi

cd "$SCRIPT_DIR"
echo -e "${GREEN}Script completed successfully!${NC}"
