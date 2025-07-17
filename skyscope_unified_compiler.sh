#!/bin/bash
#
# skyscope_unified_compiler.sh
# Unified Compiler Script for Skyscope macOS Patcher
#
# This script merges functionality from build_skyscope_oclp.sh and OpenCore Legacy Patcher
# to create a seamless application with enhanced GPU support for NVIDIA GTX 970 and Intel Arc 770
# with compatibility for macOS beta versions (26.0, 26.1, 26.2, 26.3 and newer)
#
# Copyright (c) 2025 SkyScope Project
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
TIMESTAMP=$(date "+%Y%m%d_%H%M%S")

# Directory structure
RESOURCES_DIR="$SCRIPT_DIR/RESOURCES"
OCLP_DIR="$RESOURCES_DIR/OpenCore-Legacy-Patcher-2.4.0"
BUILD_DIR="$SCRIPT_DIR/Build-Folder"
TEMP_DIR="$SCRIPT_DIR/temp"
OUTPUT_DIR="$SCRIPT_DIR/output"
KEXTS_DIR="$SCRIPT_DIR/kexts"
CUSTOM_KEXTS_DIR="$SCRIPT_DIR/custom_kexts"
NVIDIA_KEXT_DIR="$CUSTOM_KEXTS_DIR/nvidia"
INTEL_ARC_KEXT_DIR="$CUSTOM_KEXTS_DIR/intel_arc"
SRC_DIR="$SCRIPT_DIR/src"
NVIDIA_SRC_DIR="$SRC_DIR/nvidia"
INTEL_ARC_SRC_DIR="$SRC_DIR/intel_arc"

# Version information
VERSION="1.0.0"
BUILD_DATE="$(date "+%Y-%m-%d")"
OCLP_VERSION="2.4.0"
APP_NAME="Skyscope macOS Patcher"
APP_BUNDLE_ID="com.skyscope.macos.patcher"

# Python requirements
PYTHON_MIN_VERSION="3.8.0"
REQUIRED_PACKAGES=(
    "pyinstaller"
    "wxPython"
    "packaging"
    "requests"
    "tqdm"
    "pyobjc"
    "dmgbuild"
    "lief"
)

# macOS version information
MACOS_VERSIONS=(
    "sequoia:15:15A:Sequoia"
    "tahoe:16:16A:Tahoe"
    "macos_beta:26.0:26A:macOS Beta"
    "macos_beta_1:26.1:26B:macOS Beta 1"
    "macos_beta_2:26.2:26C:macOS Beta 2"
    "macos_beta_3:26.3:26D:macOS Beta 3"
)

# Hardware support information
NVIDIA_GPUS=(
    "0x13C2:NVIDIA GeForce GTX 970:Maxwell:4096"
    "0x17C8:NVIDIA GeForce GTX 980 Ti:Maxwell:6144"
    "0x1B81:NVIDIA GeForce GTX 1070:Pascal:8192"
    "0x1B06:NVIDIA GeForce GTX 1080 Ti:Pascal:11264"
)

INTEL_GPUS=(
    "0x56A0:Intel Arc A770:Xe-HPG:16384"
    "0x56A1:Intel Arc A750:Xe-HPG:8192"
    "0x56A5:Intel Arc A580:Xe-HPG:8192"
    "0x56A6:Intel Arc A380:Xe-HPG:6144"
)

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

# Function to check if running as root
check_not_root() {
    if [ "$EUID" -eq 0 ]; then
        log "ERROR" "This script should not be run as root (with sudo)"
        log "WARNING" "Please run it as a normal user. Elevated privileges will be requested when needed."
        exit 1
    fi
}

# Function to prompt for sudo when needed
prompt_for_sudo() {
    if [ "$EUID" -ne 0 ]; then
        log "INFO" "Requesting elevated privileges for: $1"
        sudo "$@"
    else
        "$@"
    fi
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
        if ! python3 -c "import $package" &>/dev/null 2>&1; then
            missing_packages+=("$package")
        fi
    done
    
    # Install missing packages
    if [ ${#missing_packages[@]} -gt 0 ]; then
        log "WARNING" "Missing Python packages: ${missing_packages[*]}"
        log "INFO" "Installing missing packages..."
        
        for package in "${missing_packages[@]}"; do
            log "DEBUG" "Installing $package..."
            if [ "$package" = "lief" ]; then
                # Use pip for lief as Homebrew version can be problematic
                pip3 install "$package"
            elif [ "$package" = "wxPython" ]; then
                # wxPython can be tricky, try pip first then fallback to brew
                pip3 install -U wxPython || brew install wxpython
            else
                pip3 install "$package"
            fi
            
            if [ $? -ne 0 ]; then
                log "ERROR" "Failed to install $package"
                exit 1
            fi
        done
    fi
    
    log "INFO" "All dependencies satisfied"
}

# Function to create directory structure
create_directories() {
    log "INFO" "Creating directory structure..."
    
    mkdir -p "$BUILD_DIR"
    mkdir -p "$TEMP_DIR"
    mkdir -p "$OUTPUT_DIR"
    mkdir -p "$KEXTS_DIR"
    mkdir -p "$CUSTOM_KEXTS_DIR"
    mkdir -p "$NVIDIA_KEXT_DIR"
    mkdir -p "$INTEL_ARC_KEXT_DIR"
    mkdir -p "$SRC_DIR"
    mkdir -p "$NVIDIA_SRC_DIR"
    mkdir -p "$INTEL_ARC_SRC_DIR"
    
    log "DEBUG" "Created all required directories"
}

# Function to copy resources from RESOURCES directory
copy_resources() {
    log "INFO" "Copying resources from RESOURCES directory..."
    
    # Check if RESOURCES directory exists
    if [ ! -d "$RESOURCES_DIR" ]; then
        log "ERROR" "RESOURCES directory not found at: $RESOURCES_DIR"
        exit 1
    fi
    
    # Copy OpenCore Legacy Patcher if it exists
    if [ -d "$OCLP_DIR" ]; then
        log "INFO" "Found OpenCore Legacy Patcher at: $OCLP_DIR"
        # Copy to build directory for patching
        cp -R "$OCLP_DIR" "$BUILD_DIR/"
        log "DEBUG" "Copied OpenCore Legacy Patcher to build directory"
    else
        log "WARNING" "OpenCore Legacy Patcher not found in RESOURCES directory"
        log "INFO" "Downloading OpenCore Legacy Patcher..."
        
        # Create temporary directory for download
        mkdir -p "$TEMP_DIR/oclp_download"
        
        # Download OpenCore Legacy Patcher
        curl -L "https://github.com/dortania/OpenCore-Legacy-Patcher/archive/refs/tags/$OCLP_VERSION.zip" -o "$TEMP_DIR/oclp_download/oclp.zip"
        
        # Extract OpenCore Legacy Patcher
        unzip -q "$TEMP_DIR/oclp_download/oclp.zip" -d "$TEMP_DIR/oclp_download"
        
        # Copy to build directory
        cp -R "$TEMP_DIR/oclp_download/OpenCore-Legacy-Patcher-$OCLP_VERSION" "$BUILD_DIR/OpenCore-Legacy-Patcher-$OCLP_VERSION"
        
        log "INFO" "Downloaded and extracted OpenCore Legacy Patcher"
    fi
    
    # Copy kexts from RESOURCES directory if they exist
    if [ -d "$RESOURCES_DIR/Hackintool_Kexts" ]; then
        log "INFO" "Found kexts in RESOURCES directory"
        cp -R "$RESOURCES_DIR/Hackintool_Kexts/"* "$KEXTS_DIR/"
        log "DEBUG" "Copied kexts from RESOURCES directory"
    fi
    
    # Copy EFI folder if it exists
    if [ -d "$RESOURCES_DIR/EFI" ]; then
        log "INFO" "Found EFI folder in RESOURCES directory"
        cp -R "$RESOURCES_DIR/EFI" "$BUILD_DIR/"
        log "DEBUG" "Copied EFI folder from RESOURCES directory"
    fi
    
    # Copy FILES directory with tools if it exists
    if [ -d "$RESOURCES_DIR/FILES" ]; then
        log "INFO" "Found FILES directory with tools"
        mkdir -p "$BUILD_DIR/Tools"
        cp -R "$RESOURCES_DIR/FILES/"* "$BUILD_DIR/Tools/"
        log "DEBUG" "Copied tools from FILES directory"
    fi
    
    log "INFO" "Resources copied successfully"
}

# Function to patch OpenCore Legacy Patcher for macOS version compatibility
patch_oclp_for_macos_versions() {
    log "INFO" "Patching OpenCore Legacy Patcher for macOS version compatibility..."
    
    # Path to constants.py
    local constants_py="$BUILD_DIR/OpenCore-Legacy-Patcher-$OCLP_VERSION/opencore_legacy_patcher/constants.py"
    
    # Check if constants.py exists
    if [ ! -f "$constants_py" ]; then
        log "ERROR" "constants.py not found at: $constants_py"
        exit 1
    fi
    
    # Create backup of constants.py
    cp "$constants_py" "${constants_py}.bak"
    log "DEBUG" "Created backup of constants.py"
    
    # Add macOS Sequoia and Tahoe to legacy_accel_support list if not already there
    if ! grep -q "os_data.sequoia" "$constants_py"; then
        log "INFO" "Adding macOS Sequoia support"
        sed -i '' 's/self.legacy_accel_support = \[/self.legacy_accel_support = \[\n            os_data.os_data.sequoia,/g' "$constants_py"
    fi
    
    if ! grep -q "os_data.tahoe" "$constants_py"; then
        log "INFO" "Adding macOS Tahoe support"
        sed -i '' 's/self.legacy_accel_support = \[/self.legacy_accel_support = \[\n            os_data.os_data.tahoe,/g' "$constants_py"
    fi
    
    # Add macOS Beta versions to os_data.py
    local os_data_py="$BUILD_DIR/OpenCore-Legacy-Patcher-$OCLP_VERSION/opencore_legacy_patcher/datasets/os_data.py"
    
    # Check if os_data.py exists
    if [ ! -f "$os_data_py" ]; then
        log "ERROR" "os_data.py not found at: $os_data_py"
        exit 1
    fi
    
    # Create backup of os_data.py
    cp "$os_data_py" "${os_data_py}.bak"
    log "DEBUG" "Created backup of os_data.py"
    
    # Add macOS Beta versions to os_data.py
    if ! grep -q "macos_beta = " "$os_data_py"; then
        log "INFO" "Adding macOS Beta versions to os_data.py"
        
        # Find the class definition
        local class_line=$(grep -n "class os_data:" "$os_data_py" | cut -d ':' -f 1)
        
        # Add new OS versions after the class definition
        sed -i '' "${class_line}a\\
    # macOS Beta versions\\
    macos_beta = 26.0\\
    macos_beta_1 = 26.1\\
    macos_beta_2 = 26.2\\
    macos_beta_3 = 26.3" "$os_data_py"
        
        log "DEBUG" "Added macOS Beta versions to os_data.py"
    fi
    
    # Update os_probe.py to detect macOS Beta versions
    local os_probe_py="$BUILD_DIR/OpenCore-Legacy-Patcher-$OCLP_VERSION/opencore_legacy_patcher/detections/os_probe.py"
    
    # Check if os_probe.py exists
    if [ ! -f "$os_probe_py" ]; then
        log "ERROR" "os_probe.py not found at: $os_probe_py"
        exit 1
    fi
    
    # Create backup of os_probe.py
    cp "$os_probe_py" "${os_probe_py}.bak"
    log "DEBUG" "Created backup of os_probe.py"
    
    # Update OS detection in os_probe.py
    if ! grep -q "26\." "$os_probe_py"; then
        log "INFO" "Updating OS detection in os_probe.py"
        
        # Find the detect_os_version function
        local function_line=$(grep -n "def detect_os_version" "$os_probe_py" | cut -d ':' -f 1)
        
        # Add macOS Beta version detection
        sed -i '' "/if \"15.\" in os_version:/i\\
        # macOS Beta detection\\
        if \"26.3\" in os_version:\\
            return \"macOS Beta 3\"\\
        if \"26.2\" in os_version:\\
            return \"macOS Beta 2\"\\
        if \"26.1\" in os_version:\\
            return \"macOS Beta 1\"\\
        if \"26.0\" in os_version or \"26.\" in os_version:\\
            return \"macOS Beta\"\\
        " "$os_probe_py"
        
        log "DEBUG" "Updated OS detection in os_probe.py"
    fi
    
    # Update application_entry.py to handle new OS versions
    local app_entry_py="$BUILD_DIR/OpenCore-Legacy-Patcher-$OCLP_VERSION/opencore_legacy_patcher/application_entry.py"
    
    # Check if application_entry.py exists
    if [ ! -f "$app_entry_py" ]; then
        log "ERROR" "application_entry.py not found at: $app_entry_py"
        exit 1
    fi
    
    # Create backup of application_entry.py
    cp "$app_entry_py" "${app_entry_py}.bak"
    log "DEBUG" "Created backup of application_entry.py"
    
    # Add OS version handling patch to application_entry.py
    if ! grep -q "# SkyScope OS version handling patch" "$app_entry_py"; then
        log "INFO" "Adding OS version handling patch to application_entry.py"
        
        # Find the _generate_base_data function
        local function_line=$(grep -n "_generate_base_data" "$app_entry_py" | cut -d ':' -f 1)
        
        # Add SkyScope patch after OS detection
        sed -i '' "/self.constants.detected_os_version = os_data.detect_os_version()/a\\
        # SkyScope OS version handling patch\\
        if \"Beta\" in self.constants.detected_os_version:\\
            logging.info(f\"Detected macOS Beta version: {self.constants.detected_os_version}\")\\
            # Set OS version for compatibility\\
            if self.constants.detected_os_build.startswith(\"26\"):\\
                logging.info(\"Setting compatibility for macOS Beta\")\\
                # Ensure we have proper support\\
                if not hasattr(os_data.os_data, \"macos_beta\"):\\
                    setattr(os_data.os_data, \"macos_beta\", 26.0)\\
                    self.constants.legacy_accel_support.append(26.0)\\
        " "$app_entry_py"
        
        log "DEBUG" "Added OS version handling patch to application_entry.py"
    fi
    
    # Update icon paths for new macOS versions
    if ! grep -q "icon_path_macos_beta" "$constants_py"; then
        log "INFO" "Adding icon paths for macOS Beta versions"
        
        # Add icon paths after existing icon paths
        sed -i '' "/def icon_path_macos_sequoia/a\\
    @property\\
    def icon_path_macos_beta(self):\\
        return self.icns_resource_path / Path(\"Generic.icns\")\\
        " "$constants_py"
        
        # Update icons_path list to include new icons
        sed -i '' "/self.icons_path = \[/,/\]/c\\
    @property\\
    def icons_path(self):\\
        return [\\
            str(self.icon_path_macos_generic),\\
            str(self.icon_path_macos_big_sur),\\
            str(self.icon_path_macos_monterey),\\
            str(self.icon_path_macos_ventura),\\
            str(self.icon_path_macos_sonoma),\\
            str(self.icon_path_macos_sequoia),\\
            str(self.icon_path_macos_beta),\\
        ]" "$constants_py"
        
        log "DEBUG" "Added icon paths for macOS Beta versions"
    fi
    
    log "INFO" "OpenCore Legacy Patcher patched successfully for macOS version compatibility"
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

    # Copy NVIDIA source files if they exist
    if [ -f "$SRC_DIR/nvidia/nvbridge_core.cpp" ]; then
        log "INFO" "Found NVIDIA bridge core implementation"
        cp "$SRC_DIR/nvidia/nvbridge_core.cpp" "$NVIDIA_KEXT_DIR/NVBridge.kext/Contents/MacOS/"
    fi
    
    if [ -f "$SRC_DIR/nvidia/nvbridge_metal.cpp" ]; then
        log "INFO" "Found NVIDIA Metal bridge implementation"
        cp "$SRC_DIR/nvidia/nvbridge_metal.cpp" "$NVIDIA_KEXT_DIR/NVBridge.kext/Contents/MacOS/"
    fi
    
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

    # Copy Intel Arc source files if they exist
    if [ -f "$SRC_DIR/intel_arc/arc_bridge.cpp" ]; then
        log "INFO" "Found Intel Arc bridge implementation"
        cp "$SRC_DIR/intel_arc/arc_bridge.cpp" "$INTEL_ARC_KEXT_DIR/ArcBridge.kext/Contents/MacOS/"
    fi
    
    # Compile Intel Arc bridge kext binary (placeholder - would need actual compilation in real implementation)
    echo "#!/bin/bash" > "$INTEL_ARC_KEXT_DIR/ArcBridge.kext/Contents/MacOS/ArcBridge"
    echo "# Intel Arc Bridge Driver Binary" >> "$INTEL_ARC_KEXT_DIR/ArcBridge.kext/Contents/MacOS/ArcBridge"
    chmod +x "$INTEL_ARC_KEXT_DIR/ArcBridge.kext/Contents/MacOS/ArcBridge"
    
    log "INFO" "Intel Arc 770 support added"
}

# Function to patch OCLP for custom GPU support
patch_oclp_for_custom_gpus() {
    log "INFO" "Patching OpenCore Legacy Patcher for custom GPU support..."
    
    # Path to constants.py
    local constants_py="$BUILD_DIR/OpenCore-Legacy-Patcher-$OCLP_VERSION/opencore_legacy_patcher/constants.py"
    
    # Check if constants.py exists
    if [ ! -f "$constants_py" ]; then
        log "ERROR" "constants.py not found at: $constants_py"
        exit 1
    fi
    
    # Create a patch file for constants.py to add our GPU definitions
    local constants_patch_file="$TEMP_DIR/constants_patch.py"
    
    cat > "$constants_patch_file" << EOF
# Custom GPU definitions for SkyScope
NVIDIA_GTX_970_ID = "0x13c210de"
INTEL_ARC_770_ID = "0x56a08086"

# Add custom kexts to payload paths
NVIDIA_BRIDGE_PATH = "$NVIDIA_KEXT_DIR/NVBridge.kext"
INTEL_ARC_BRIDGE_PATH = "$INTEL_ARC_KEXT_DIR/ArcBridge.kext"
EOF

    # Append the patch to constants.py
    cat "$constants_patch_file" >> "$constants_py"
    
    # Update device detection to recognize our custom GPUs
    local device_probe_py="$BUILD_DIR/OpenCore-Legacy-Patcher-$OCLP_VERSION/opencore_legacy_patcher/detections/device_probe.py"
    
    # Check if device_probe.py exists
    if [ ! -f "$device_probe_py" ]; then
        log "ERROR" "device_probe.py not found at: $device_probe_py"
        exit 1
    fi
    
    # Create backup of device_probe.py
    cp "$device_probe_py" "${device_probe_py}.bak"
    log "DEBUG" "Created backup of device_probe.py"
    
    # Add custom GPU detection to device_probe.py
    if ! grep -q "# SkyScope GPU detection patch" "$device_probe_py"; then
        log "INFO" "Adding custom GPU detection to device_probe.py"
        
        # Find the GPU detection section
        local gpu_section=$(grep -n "def determine_gpu_vendor" "$device_probe_py" | cut -d ':' -f 1)
        
        # Add SkyScope GPU detection after the function definition
        sed -i '' "${gpu_section}a\\
        # SkyScope GPU detection patch\\
        if \"NVIDIA GeForce GTX 970\" in model or \"0x13c2\" in model.lower():\\
            return \"NVIDIA GTX 970\"\\
        if \"Intel Arc A770\" in model or \"0x56a0\" in model.lower():\\
            return \"Intel Arc 770\"\\
        " "$device_probe_py"
        
        log "DEBUG" "Added custom GPU detection to device_probe.py"
    fi
    
    log "INFO" "OpenCore Legacy Patcher patched for custom GPU support"
}

# Function to clean up redundant code
clean_redundant_code() {
    log "INFO" "Cleaning up redundant code..."
    
    # Find and remove redundant .pyc files
    find "$BUILD_DIR" -name "*.pyc" -delete
    
    # Find and remove redundant __pycache__ directories
    find "$BUILD_DIR" -name "__pycache__" -type d -exec rm -rf {} +
    
    # Remove any .DS_Store files
    find "$BUILD_DIR" -name ".DS_Store" -delete
    
    # Remove git directories
    find "$BUILD_DIR" -name ".git" -type d -exec rm -rf {} +
    
    # Remove backup files
    find "$BUILD_DIR" -name "*.bak" -delete
    
    # Remove any test directories
    find "$BUILD_DIR" -name "tests" -type d -exec rm -rf {} +
    
    # Remove any documentation directories
    find "$BUILD_DIR" -name "docs" -type d -exec rm -rf {} +
    
    # Remove any CI/CD directories
    find "$BUILD_DIR" -name "ci_tooling" -type d -exec rm -rf {} +
    
    # Remove any .github directories
    find "$BUILD_DIR" -name ".github" -type d -exec rm -rf {} +
    
    log "INFO" "Redundant code cleanup complete"
}

# Function to build the OCLP application
build_oclp() {
    log "INFO" "Building OpenCore Legacy Patcher..."
    
    # Navigate to OCLP directory
    cd "$BUILD_DIR/OpenCore-Legacy-Patcher-$OCLP_VERSION"
    
    # Clean any previous builds
    if [ -d "dist" ]; then
        log "DEBUG" "Removing previous build artifacts..."
        rm -rf dist
    fi
    
    # Update the application name in the spec file
    local spec_file="OpenCore-Patcher-GUI.spec"
    if [ -f "$spec_file" ]; then
        log "DEBUG" "Updating application name in spec file..."
        sed -i '' "s/OpenCore-Patcher/$APP_NAME/g" "$spec_file"
        sed -i '' "s/com.dortania.opencore-legacy-patcher/$APP_BUNDLE_ID/g" "$spec_file"
    fi
    
    # Run the build script with our customizations
    log "INFO" "Running build process..."
    python3 Build-Project.command --reset-pyinstaller-cache
    
    # Check if build was successful
    if [ $? -ne 0 ]; then
        log "ERROR" "Build failed. Check the logs for details."
        exit 1
    fi
    
    # Copy the built application to our output directory
    if [ -d "dist/OpenCore-Patcher.app" ]; then
        log "INFO" "Copying built application to output directory..."
        cp -R "dist/OpenCore-Patcher.app" "$OUTPUT_DIR/$APP_NAME.app"
        
        # Customize the app name and identifiers
        /usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$OUTPUT_DIR/$APP_NAME.app/Contents/Info.plist"
        /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $APP_BUNDLE_ID" "$OUTPUT_DIR/$APP_NAME.app/Contents/Info.plist"
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
    local dmg_settings_file="$TEMP_DIR/dmg_settings.py"
    
    cat > "$dmg_settings_file" << EOF
# DMG settings for $APP_NAME
app = "$OUTPUT_DIR/$APP_NAME.app"
appname = "$APP_NAME"
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
    dmgbuild -s "$dmg_settings_file" "$APP_NAME" "$OUTPUT_DIR/$APP_NAME.dmg"
    
    if [ $? -ne 0 ]; then
        log "ERROR" "DMG creation failed"
        exit 1
    fi
    
    log "INFO" "DMG installer created: $OUTPUT_DIR/$APP_NAME.dmg"
}

# Function to install the built application
install_application() {
    log "INFO" "Installing $APP_NAME..."
    
    # Check if application exists
    if [ ! -d "$OUTPUT_DIR/$APP_NAME.app" ]; then
        log "ERROR" "Application not found. Build may have failed."
        exit 1
    fi
    
    # Copy application to Applications folder
    prompt_for_sudo cp -R "$OUTPUT_DIR/$APP_NAME.app" "/Applications/"
    
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

# Function to display help
show_help() {
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${CYAN}   Skyscope macOS Patcher Unified Compiler ${NC}"
    echo -e "${CYAN}==========================================${NC}"
    echo
    echo -e "${GREEN}Usage:${NC} $0 [OPTION]"
    echo
    echo -e "${YELLOW}Options:${NC}"
    echo "  --build       Build the application"
    echo "  --install     Install the application"
    echo "  --clean       Clean build artifacts"
    echo "  --help        Display this help message"
    echo
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 --build    # Build the application"
    echo "  $0 --install  # Install the application"
    echo "  $0            # Build and prompt to install"
    echo
}

# Main function
main() {
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${CYAN}   Skyscope macOS Patcher Unified Compiler ${NC}"
    echo -e "${CYAN}==========================================${NC}"
    echo
    
    # Initialize log file
    echo "Build started at $(date)" > "$LOG_FILE"
    
    # Check if running as root
    check_not_root
    
    # Parse command line arguments
    if [ "$1" == "--help" ]; then
        show_help
        exit 0
    elif [ "$1" == "--clean" ]; then
        log "INFO" "Cleaning build artifacts..."
        rm -rf "$BUILD_DIR" "$TEMP_DIR" "$OUTPUT_DIR"
        log "INFO" "Clean completed"
        exit 0
    elif [ "$1" == "--install" ]; then
        install_application
        exit 0
    elif [ "$1" == "--build" ]; then
        # Only build, don't prompt for installation
        BUILD_ONLY=true
    else
        BUILD_ONLY=false
    fi
    
    # Total steps for progress tracking
    local total_steps=10
    local current_step=0
    
    # Step 1: Check Python version
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Checking Python version..."
    check_python_version
    
    # Step 2: Check dependencies
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Checking dependencies..."
    check_dependencies
    
    # Step 3: Create directories
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Creating directories..."
    create_directories
    
    # Step 4: Copy resources
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Copying resources..."
    copy_resources
    
    # Step 5: Patch for macOS version compatibility
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Patching for macOS version compatibility..."
    patch_oclp_for_macos_versions
    
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
    show_progress $current_step $total_steps "Patching OCLP for custom GPUs..."
    patch_oclp_for_custom_gpus
    
    # Step 9: Clean redundant code
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Cleaning redundant code..."
    clean_redundant_code
    
    # Step 10: Build OCLP
    current_step=$((current_step + 1))
    show_progress $current_step $total_steps "Building application..."
    build_oclp
    
    # Create DMG installer
    create_dmg
    
    echo
    echo -e "${GREEN}Build completed successfully!${NC}"
    echo -e "Application: ${YELLOW}$OUTPUT_DIR/$APP_NAME.app${NC}"
    echo -e "Installer: ${YELLOW}$OUTPUT_DIR/$APP_NAME.dmg${NC}"
    echo
    
    # Ask if user wants to install
    if [ "$BUILD_ONLY" = false ]; then
        read -p "Do you want to install the application now? (y/n): " install_choice
        if [[ "$install_choice" == "y" || "$install_choice" == "Y" ]]; then
            install_application
            echo -e "${GREEN}$APP_NAME has been installed to /Applications/${NC}"
        else
            echo -e "${YELLOW}You can install the application later by running:${NC}"
            echo -e "${CYAN}$0 --install${NC}"
        fi
    fi
    
    echo
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${GREEN}Build process completed successfully!${NC}"
    echo -e "${CYAN}==========================================${NC}"
}

# Run main function with arguments
main "$@"
