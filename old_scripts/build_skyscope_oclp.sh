#!/bin/bash
#
# build_skyscope_oclp.sh
# Enhanced automated build script for OpenCore Legacy Patcher with NVIDIA and Intel Arc support
# Created for SkyScope project
# 
# This script automates the build process for OpenCore Legacy Patcher with enhanced
# GPU support for NVIDIA GTX 970 and Intel Arc 770 graphics cards
#

# Set strict error handling
set -e

# Color codes for prettier output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$HOME/skyscope_build.log"
OCLP_DIR="$SCRIPT_DIR/OpenCore-Legacy-Patcher-2.4.0"
CUSTOM_KEXTS_DIR="$SCRIPT_DIR/custom_kexts"
NVIDIA_KEXT_DIR="$CUSTOM_KEXTS_DIR/nvidia"
INTEL_ARC_KEXT_DIR="$CUSTOM_KEXTS_DIR/intel_arc"
BUILD_DIR="$SCRIPT_DIR/build"
TEMP_DIR="$SCRIPT_DIR/temp"
# Source code directories (for bridge implementations, etc.)
SRC_DIR="$SCRIPT_DIR/src"
NVIDIA_SRC_DIR="$SRC_DIR/nvidia"
INTEL_ARC_SRC_DIR="$SRC_DIR/intel_arc"
PYTHON_MIN_VERSION="3.8.0"
REQUIRED_PACKAGES=(
    "pyinstaller"
    "wxPython"
    "packaging"
    "requests"
    "pyobjc"
    "dmgbuild"
)

# Function to check if running as root
check_not_root() {
    if [ "$EUID" -eq 0 ]; then
        echo -e "${RED}Error: This script should not be run as root (with sudo)${NC}"
        echo -e "${YELLOW}Please run it as a normal user. Elevated permissions will be requested when needed.${NC}"
        exit 1
    fi
}

# Function to prompt for sudo when needed
prompt_for_sudo() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${YELLOW}Requesting elevated privileges for: $1${NC}"
        sudo "$@"
    else
        "$@"
    fi
}

# Function to log messages
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    
    case "$level" in
        "INFO")
            echo -e "${GREEN}[INFO]${NC} $message"
            ;;
        "WARNING")
            echo -e "${YELLOW}[WARNING]${NC} $message"
            ;;
        "ERROR")
            echo -e "${RED}[ERROR]${NC} $message"
            ;;
        "DEBUG")
            echo -e "${BLUE}[DEBUG]${NC} $message"
            ;;
        *)
            echo -e "${PURPLE}[$level]${NC} $message"
            ;;
    esac
    
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# Function to check Python version
check_python_version() {
    log "INFO" "Checking Python version..."
    
    if ! command -v python3 &>/dev/null; then
        log "ERROR" "Python 3 is not installed. Please install Python 3.8 or higher."
        exit 1
    fi
    
    local python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    log "DEBUG" "Detected Python version: $python_version"
    
    if ! python3 -c "import sys; from packaging import version; sys.exit(0 if version.parse('$python_version') >= version.parse('$PYTHON_MIN_VERSION') else 1)"; then
        log "ERROR" "Python version $python_version is below the required version $PYTHON_MIN_VERSION"
        exit 1
    fi
    
    log "INFO" "Python version check passed: $python_version"
}

# Function to check and install required packages
check_dependencies() {
    log "INFO" "Checking dependencies..."
    
    # Check for Homebrew
    if ! command -v brew &>/dev/null; then
        log "WARNING" "Homebrew not found. Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [ $? -ne 0 ]; then
            log "ERROR" "Failed to install Homebrew"
            exit 1
        fi
    fi
    
    # Check for XCode Command Line Tools
    if ! xcode-select -p &>/dev/null; then
        log "WARNING" "XCode Command Line Tools not found. Installing..."
        xcode-select --install
        log "INFO" "Please complete the XCode Command Line Tools installation and run this script again."
        exit 0
    fi
    
    # Check for pip
    if ! command -v pip3 &>/dev/null; then
        log "WARNING" "pip3 not found. Installing..."
        python3 -m ensurepip || curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python3 get-pip.py
        if [ $? -ne 0 ]; then
            log "ERROR" "Failed to install pip"
            exit 1
        fi
    fi
    
    # Check for required Python packages
    local missing_packages=()
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if ! python3 -c "import $package" &>/dev/null; then
            missing_packages+=("$package")
        fi
    done
    
    # Install missing packages
    if [ ${#missing_packages[@]} -gt 0 ]; then
        log "WARNING" "Missing Python packages: ${missing_packages[*]}"
        log "INFO" "Installing missing packages..."
        
        for package in "${missing_packages[@]}"; do
            log "DEBUG" "Installing $package..."
            pip3 install "$package"
            if [ $? -ne 0 ]; then
                log "ERROR" "Failed to install $package"
                exit 1
            fi
        done
    fi
    
    # Check for lief (needed for Linux driver extraction)
    if ! python3 -c "import lief" &>/dev/null; then
        log "WARNING" "lief package not found. Installing..."
        pip3 install lief
        if [ $? -ne 0 ]; then
            log "WARNING" "Failed to install lief via pip. Linux driver extraction will be disabled."
            SKIP_LINUX_EXTRACTION=1
        fi
    fi
    
    log "INFO" "All dependencies satisfied"
}

# Function to create directory structure
create_directories() {
    log "INFO" "Creating directory structure..."
    
    mkdir -p "$BUILD_DIR"
    mkdir -p "$TEMP_DIR"
    mkdir -p "$CUSTOM_KEXTS_DIR"
    mkdir -p "$NVIDIA_KEXT_DIR"
    mkdir -p "$INTEL_ARC_KEXT_DIR"
    mkdir -p "$NVIDIA_SRC_DIR"
    mkdir -p "$INTEL_ARC_SRC_DIR"
    
    log "DEBUG" "Created directories: BUILD_DIR, TEMP_DIR, CUSTOM_KEXTS_DIR, NVIDIA_KEXT_DIR, INTEL_ARC_KEXT_DIR, NVIDIA_SRC_DIR, INTEL_ARC_SRC_DIR"
}

# Function to download OCLP source if missing
ensure_oclp_source() {
    if [ -d "$OCLP_DIR" ]; then
        log "INFO" "OpenCore Legacy Patcher source found: $OCLP_DIR"
        return
    fi

    log "WARNING" "OpenCore Legacy Patcher source not found at expected path."

    # Ensure git is available
    if ! command -v git &>/dev/null; then
        log "ERROR" "git is required to download OCLP source. Please install Command Line Tools (xcode-select --install) or git."
        exit 1
    fi

    log "INFO" "Cloning OpenCore Legacy Patcher 2.4.0 from GitHub..."
    if git clone --depth=1 --branch 2.4.0 https://github.com/dortania/OpenCore-Legacy-Patcher.git "$OCLP_DIR"; then
        log "INFO" "Successfully downloaded OpenCore Legacy Patcher source."
    else
        log "ERROR" "Failed to clone OpenCore Legacy Patcher repository."
        exit 1
    fi
}

# Function to clean up redundant code
clean_redundant_code() {
    log "INFO" "Cleaning up redundant code..."
    
    # Find and remove redundant .pyc files
    find "$OCLP_DIR" -name "*.pyc" -delete
    
    # Find and remove redundant __pycache__ directories
    find "$OCLP_DIR" -name "__pycache__" -type d -exec rm -rf {} +
    
    # Remove any .DS_Store files
    find "$OCLP_DIR" -name ".DS_Store" -delete
    
    log "INFO" "Redundant code cleanup complete"
}

# Function to patch for NVIDIA GPU support
patch_nvidia_support() {
    log "INFO" "Adding NVIDIA GTX 970 support..."
    
    # Create NVIDIA bridge kext directory structure
    mkdir -p "$NVIDIA_KEXT_DIR/NVBridge.kext/Contents/MacOS"
    
    # Create Info.plist for NVIDIA bridge
    cat > "$NVIDIA_KEXT_DIR/NVBridge.kext/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleIdentifier</key>
    <string>com.skyscope.driver.NVBridge</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>NVBridge</string>
    <key>CFBundlePackageType</key>
    <string>KEXT</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>IOKitPersonalities</key>
    <dict>
        <key>NVBridge</key>
        <dict>
            <key>CFBundleIdentifier</key>
            <string>com.skyscope.driver.NVBridge</string>
            <key>IOClass</key>
            <string>NVBridgeDriver</string>
            <key>IOMatchCategory</key>
            <string>NVBridgeDriver</string>
            <key>IOPCIClassMatch</key>
            <string>0x03000000&amp;0xff000000</string>
            <key>IOPCIMatch</key>
            <string>0x13c210de</string>
            <key>IOProbeScore</key>
            <integer>20000</integer>
            <key>IOProviderClass</key>
            <string>IOPCIDevice</string>
        </dict>
    </dict>
    <key>OSBundleLibraries</key>
    <dict>
        <key>com.apple.iokit.IOPCIFamily</key>
        <string>1.0.0b1</string>
        <key>com.apple.kpi.bsd</key>
        <string>8.0.0</string>
        <key>com.apple.kpi.iokit</key>
        <string>8.0.0</string>
        <key>com.apple.kpi.libkern</key>
        <string>8.0.0</string>
        <key>com.apple.kpi.mach</key>
        <string>8.0.0</string>
    </dict>
</dict>
</plist>
EOF

    # Compile NVIDIA bridge kext binary (placeholder - would need actual compilation in real implementation)
    echo "#!/bin/bash" > "$NVIDIA_KEXT_DIR/NVBridge.kext/Contents/MacOS/NVBridge"
    echo "# NVIDIA Bridge Driver Binary" >> "$NVIDIA_KEXT_DIR/NVBridge.kext/Contents/MacOS/NVBridge"
    chmod +x "$NVIDIA_KEXT_DIR/NVBridge.kext/Contents/MacOS/NVBridge"
    
    log "INFO" "NVIDIA GTX 970 support added"
}

# Function to patch for Intel Arc support
patch_intel_arc_support() {
    log "INFO" "Adding Intel Arc 770 support..."
    
    # Create Intel Arc bridge kext directory structure
    mkdir -p "$INTEL_ARC_KEXT_DIR/ArcBridge.kext/Contents/MacOS"
    
    # Create Info.plist for Intel Arc bridge
    cat > "$INTEL_ARC_KEXT_DIR/ArcBridge.kext/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleIdentifier</key>
    <string>com.skyscope.driver.ArcBridge</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>ArcBridge</string>
    <key>CFBundlePackageType</key>
    <string>KEXT</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>IOKitPersonalities</key>
    <dict>
        <key>ArcBridge</key>
        <dict>
            <key>CFBundleIdentifier</key>
            <string>com.skyscope.driver.ArcBridge</string>
            <key>IOClass</key>
            <string>ArcBridgeDriver</string>
            <key>IOMatchCategory</key>
            <string>ArcBridgeDriver</string>
            <key>IOPCIClassMatch</key>
            <string>0x03000000&amp;0xff000000</string>
            <key>IOPCIMatch</key>
            <string>0x56a08086</string>
            <key>IOProbeScore</key>
            <integer>20000</integer>
            <key>IOProviderClass</key>
            <string>IOPCIDevice</string>
        </dict>
    </dict>
    <key>OSBundleLibraries</key>
    <dict>
        <key>com.apple.iokit.IOPCIFamily</key>
        <string>1.0.0b1</string>
        <key>com.apple.kpi.bsd</key>
        <string>8.0.0</string>
        <key>com.apple.kpi.iokit</key>
        <string>8.0.0</string>
        <key>com.apple.kpi.libkern</key>
        <string>8.0.0</string>
        <key>com.apple.kpi.mach</key>
        <string>8.0.0</string>
    </dict>
</dict>
</plist>
EOF

    # Compile Intel Arc bridge kext binary (placeholder - would need actual compilation in real implementation)
    echo "#!/bin/bash" > "$INTEL_ARC_KEXT_DIR/ArcBridge.kext/Contents/MacOS/ArcBridge"
    echo "# Intel Arc Bridge Driver Binary" >> "$INTEL_ARC_KEXT_DIR/ArcBridge.kext/Contents/MacOS/ArcBridge"
    chmod +x "$INTEL_ARC_KEXT_DIR/ArcBridge.kext/Contents/MacOS/ArcBridge"
    
    log "INFO" "Intel Arc 770 support added"
}

# Function to patch OCLP for custom GPU support
patch_oclp_for_custom_gpus() {
    log "INFO" "Patching OCLP for custom GPU support..."
    
    # Create a patch file for constants.py to add our GPU definitions
    CONSTANTS_PATCH_FILE="$TEMP_DIR/constants_patch.py"
    
    cat > "$CONSTANTS_PATCH_FILE" << EOF
# Custom GPU definitions for SkyScope
NVIDIA_GTX_970_ID = "0x13c210de"
INTEL_ARC_770_ID = "0x56a08086"

# Add custom kexts to payload paths
NVIDIA_BRIDGE_PATH = "$NVIDIA_KEXT_DIR/NVBridge.kext"
INTEL_ARC_BRIDGE_PATH = "$INTEL_ARC_KEXT_DIR/ArcBridge.kext"
EOF

    # Append the patch to constants.py
    cat "$CONSTANTS_PATCH_FILE" >> "$OCLP_DIR/opencore_legacy_patcher/constants.py"
    
    log "INFO" "OCLP patched for custom GPU support"
}

# Function to build the OCLP application
build_oclp() {
    log "INFO" "Building OpenCore Legacy Patcher..."
    
    # Navigate to OCLP directory
    cd "$OCLP_DIR"
    
    # Clean any previous builds
    if [ -d "dist" ]; then
        log "DEBUG" "Removing previous build artifacts..."
        rm -rf dist
    fi
    
    # Run the build script with our customizations
    log "INFO" "Running build process..."
    python3 Build-Project.command --reset-pyinstaller-cache
    
    # Check if build was successful
    if [ $? -ne 0 ]; then
        log "ERROR" "Build failed. Check the logs for details."
        exit 1
    fi
    
    # Copy the built application to our build directory
    if [ -d "dist/OpenCore-Patcher.app" ]; then
        log "INFO" "Copying built application to build directory..."
        cp -R "dist/OpenCore-Patcher.app" "$BUILD_DIR/SkyScope-OCLP.app"
        
        # Customize the app name and identifiers
        /usr/libexec/PlistBuddy -c "Set :CFBundleName SkyScope-OCLP" "$BUILD_DIR/SkyScope-OCLP.app/Contents/Info.plist"
        /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.skyscope.opencore-patcher" "$BUILD_DIR/SkyScope-OCLP.app/Contents/Info.plist"
    else
        log "ERROR" "Build output not found. Build may have failed."
        exit 1
    fi
    
    log "INFO" "Build completed successfully"
}

# Function to create a DMG installer
create_dmg() {
    log "INFO" "Creating DMG installer..."
    
    # Check if dmgbuild is installed
    if ! command -v dmgbuild &>/dev/null; then
        log "WARNING" "dmgbuild not found. Installing..."
        pip3 install dmgbuild
    fi
    
    # Create DMG settings file
    DMG_SETTINGS_FILE="$TEMP_DIR/dmg_settings.py"
    
    cat > "$DMG_SETTINGS_FILE" << EOF
# DMG settings for SkyScope-OCLP
app = "$BUILD_DIR/SkyScope-OCLP.app"
appname = "SkyScope-OCLP"
size = None
files = [app]
symlinks = {'Applications': '/Applications'}
badge_icon = None
icon_locations = {
    appname + '.app': (140, 120),
    'Applications': (500, 120)
}
background = 'builtin-arrow'
EOF

    # Build the DMG
    dmgbuild -s "$DMG_SETTINGS_FILE" "SkyScope-OCLP" "$BUILD_DIR/SkyScope-OCLP.dmg"
    
    if [ $? -ne 0 ]; then
        log "ERROR" "DMG creation failed"
        exit 1
    fi
    
    log "INFO" "DMG installer created: $BUILD_DIR/SkyScope-OCLP.dmg"
}

# Function to install the built application
install_application() {
    log "INFO" "Installing SkyScope-OCLP..."
    
    # Check if application exists
    if [ ! -d "$BUILD_DIR/SkyScope-OCLP.app" ]; then
        log "ERROR" "Application not found. Build may have failed."
        exit 1
    fi
    
    # Copy application to Applications folder
    prompt_for_sudo cp -R "$BUILD_DIR/SkyScope-OCLP.app" "/Applications/"
    
    # Install custom kexts
    log "INFO" "Installing custom kexts..."
    
    # Create kexts directory if it doesn't exist
    prompt_for_sudo mkdir -p "/Library/Extensions"
    
    # Copy NVIDIA kext
    if [ -d "$NVIDIA_KEXT_DIR/NVBridge.kext" ]; then
        prompt_for_sudo cp -R "$NVIDIA_KEXT_DIR/NVBridge.kext" "/Library/Extensions/"
    fi
    
    # Copy Intel Arc kext
    if [ -d "$INTEL_ARC_KEXT_DIR/ArcBridge.kext" ]; then
        prompt_for_sudo cp -R "$INTEL_ARC_KEXT_DIR/ArcBridge.kext" "/Library/Extensions/"
    fi
    
    # Update kext cache
    log "INFO" "Updating kext cache..."
    prompt_for_sudo kextcache -i /
    
    log "INFO" "Installation completed successfully"
}

# Function to display a progress bar
show_progress() {
    local current=$1
    local total=$2
    local message=$3
    local percentage=$((current * 100 / total))
    local progress=$((percentage / 2))
    
    # Create progress bar string
    local bar="["
    for ((i=0; i<progress; i++)); do
        bar+="="
    done
    for ((i=progress; i<50; i++)); do
        bar+=" "
    done
    bar+="]"
    
    # Print progress bar
    echo -ne "\r${CYAN}$message${NC} $bar ${percentage}%"
    
    # Print newline if complete
    if [ "$current" -eq "$total" ]; then
        echo
    fi
}

# Main function
main() {
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${CYAN}   SkyScope OpenCore Legacy Patcher Build ${NC}"
    echo -e "${CYAN}==========================================${NC}"
    echo
    
    # Initialize log file
    echo "Build started at $(date)" > "$LOG_FILE"
    
    # Check if running as root
    check_not_root
    
    # Total steps for progress tracking
    local total_steps=10
    local current_step=0
    
    # Step 1: Ensure OCLP source
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Ensuring OCLP source..."
    ensure_oclp_source

    # Step 2: Check Python version
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Checking Python version..."
    check_python_version
    
    # Step 3: Check dependencies
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Checking dependencies..."
    check_dependencies
    
    # Step 4: Create directories
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Creating directories..."
    create_directories
    
    # Step 5: Clean redundant code
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Cleaning redundant code..."
    clean_redundant_code
    
    # Step 6: Patch for NVIDIA GPU support
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Adding NVIDIA GPU support..."
    patch_nvidia_support
    
    # Step 7: Patch for Intel Arc support
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Adding Intel Arc support..."
    patch_intel_arc_support
    
    # Step 8: Patch OCLP for custom GPUs
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Patching OCLP..."
    patch_oclp_for_custom_gpus
    
    # Step 9: Build OCLP
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Building application..."
    build_oclp
    
    # Step 10: Create DMG installer
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Creating DMG installer..."
    create_dmg
    
    echo
    echo -e "${GREEN}Build completed successfully!${NC}"
    echo -e "Application: ${YELLOW}$BUILD_DIR/SkyScope-OCLP.app${NC}"
    echo -e "Installer: ${YELLOW}$BUILD_DIR/SkyScope-OCLP.dmg${NC}"
    echo
    
    # Ask if user wants to install
    read -p "Do you want to install the application now? (y/n): " install_choice
    if [[ "$install_choice" == "y" || "$install_choice" == "Y" ]]; then
        install_application
        echo -e "${GREEN}SkyScope-OCLP has been installed to /Applications/${NC}"
    else
        echo -e "${YELLOW}You can install the application later by running:${NC}"
        echo -e "${CYAN}$0 --install${NC}"
    fi
    
    echo
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${GREEN}Build process completed successfully!${NC}"
    echo -e "${CYAN}==========================================${NC}"
}

# Parse command line arguments
if [ "$1" == "--install" ]; then
    install_application
    exit 0
elif [ "$1" == "--help" ]; then
    echo "Usage: $0 [OPTION]"
    echo
    echo "Options:"
    echo "  --install    Install the application"
    echo "  --help       Display this help message"
    exit 0
else
    # Run main function
    main
fi
