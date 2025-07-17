#!/bin/bash
#
# clean_repo.sh
# Repository Cleanup Script for Skyscope macOS Patcher
#
# This script removes redundant files and objects from the repository,
# organizes source files, and reduces clutter in the codebase.
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
LOG_FILE="$HOME/skyscope_cleanup.log"
TIMESTAMP=$(date "+%Y%m%d_%H%M%S")

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
        log "WARNING" "Please run it as a normal user."
        exit 1
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

# Function to clean Python cache files
clean_python_cache() {
    log "INFO" "Cleaning Python cache files..."
    
    # Find and remove __pycache__ directories
    local pycache_count=$(find "$SCRIPT_DIR" -type d -name "__pycache__" | wc -l | tr -d ' ')
    log "DEBUG" "Found $pycache_count __pycache__ directories"
    find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    
    # Find and remove .pyc files
    local pyc_count=$(find "$SCRIPT_DIR" -type f -name "*.pyc" | wc -l | tr -d ' ')
    log "DEBUG" "Found $pyc_count .pyc files"
    find "$SCRIPT_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
    
    # Find and remove .pyo files
    local pyo_count=$(find "$SCRIPT_DIR" -type f -name "*.pyo" | wc -l | tr -d ' ')
    log "DEBUG" "Found $pyo_count .pyo files"
    find "$SCRIPT_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
    
    log "INFO" "Removed $pycache_count __pycache__ directories, $pyc_count .pyc files, and $pyo_count .pyo files"
}

# Function to clean macOS metadata files
clean_macos_metadata() {
    log "INFO" "Cleaning macOS metadata files..."
    
    # Find and remove .DS_Store files
    local ds_store_count=$(find "$SCRIPT_DIR" -type f -name ".DS_Store" | wc -l | tr -d ' ')
    log "DEBUG" "Found $ds_store_count .DS_Store files"
    find "$SCRIPT_DIR" -type f -name ".DS_Store" -delete 2>/dev/null || true
    
    # Find and remove ._* files
    local dotunderscore_count=$(find "$SCRIPT_DIR" -type f -name "._*" | wc -l | tr -d ' ')
    log "DEBUG" "Found $dotunderscore_count ._* files"
    find "$SCRIPT_DIR" -type f -name "._*" -delete 2>/dev/null || true
    
    log "INFO" "Removed $ds_store_count .DS_Store files and $dotunderscore_count ._* files"
}

# Function to clean build artifacts
clean_build_artifacts() {
    log "INFO" "Cleaning build artifacts..."
    
    # Define directories to clean
    local build_dirs=(
        "Build-Folder"
        "build"
        "dist"
        "output"
        "temp"
        "__pycache__"
    )
    
    # Clean each directory
    for dir in "${build_dirs[@]}"; do
        if [ -d "$SCRIPT_DIR/$dir" ]; then
            log "DEBUG" "Removing $dir directory"
            rm -rf "$SCRIPT_DIR/$dir"
        fi
    done
    
    # Clean egg-info directories
    find "$SCRIPT_DIR" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    
    # Clean log files (except the current log)
    find "$SCRIPT_DIR" -type f -name "*.log" ! -name "$(basename "$LOG_FILE")" -delete 2>/dev/null || true
    
    log "INFO" "Build artifacts cleaned"
}

# Function to clean temporary files
clean_temp_files() {
    log "INFO" "Cleaning temporary files..."
    
    # Find and remove temporary files
    local temp_patterns=(
        "*.tmp"
        "*.bak"
        "*.swp"
        "*~"
        "*.orig"
        "*.rej"
    )
    
    local total_temp_files=0
    
    for pattern in "${temp_patterns[@]}"; do
        local count=$(find "$SCRIPT_DIR" -type f -name "$pattern" | wc -l | tr -d ' ')
        total_temp_files=$((total_temp_files + count))
        find "$SCRIPT_DIR" -type f -name "$pattern" -delete 2>/dev/null || true
    done
    
    log "INFO" "Removed $total_temp_files temporary files"
}

# Function to organize source files
organize_source_files() {
    log "INFO" "Organizing source files..."
    
    # Create necessary directories if they don't exist
    mkdir -p "$SCRIPT_DIR/src/nvidia"
    mkdir -p "$SCRIPT_DIR/src/intel_arc"
    mkdir -p "$SCRIPT_DIR/src/common"
    mkdir -p "$SCRIPT_DIR/scripts"
    mkdir -p "$SCRIPT_DIR/docs"
    
    # Move NVIDIA source files to src/nvidia
    if [ -f "$SCRIPT_DIR/nvbridge_core.cpp" ]; then
        log "DEBUG" "Moving nvbridge_core.cpp to src/nvidia/"
        mv "$SCRIPT_DIR/nvbridge_core.cpp" "$SCRIPT_DIR/src/nvidia/"
    fi
    
    if [ -f "$SCRIPT_DIR/nvbridge_metal.cpp" ]; then
        log "DEBUG" "Moving nvbridge_metal.cpp to src/nvidia/"
        mv "$SCRIPT_DIR/nvbridge_metal.cpp" "$SCRIPT_DIR/src/nvidia/"
    fi
    
    if [ -f "$SCRIPT_DIR/nvbridge_cuda.cpp" ]; then
        log "DEBUG" "Moving nvbridge_cuda.cpp to src/nvidia/"
        mv "$SCRIPT_DIR/nvbridge_cuda.cpp" "$SCRIPT_DIR/src/nvidia/"
    fi
    
    # Move Intel Arc source files to src/intel_arc
    if [ -f "$SCRIPT_DIR/arc_bridge.cpp" ]; then
        log "DEBUG" "Moving arc_bridge.cpp to src/intel_arc/"
        mv "$SCRIPT_DIR/arc_bridge.cpp" "$SCRIPT_DIR/src/intel_arc/"
    fi
    
    if [ -f "$SCRIPT_DIR/intel_arc_support.py" ]; then
        log "DEBUG" "Moving intel_arc_support.py to src/intel_arc/"
        mv "$SCRIPT_DIR/intel_arc_support.py" "$SCRIPT_DIR/src/intel_arc/"
    fi
    
    # Move utility Python scripts to scripts directory
    local python_scripts=(
        "linux_extractor.py"
        "nvidia_cuda_reverse_engineer.py"
        "usb_creator.py"
        "build_gui_apps.py"
        "build_universal_apps.py"
    )
    
    for script in "${python_scripts[@]}"; do
        if [ -f "$SCRIPT_DIR/$script" ]; then
            log "DEBUG" "Moving $script to scripts/"
            mv "$SCRIPT_DIR/$script" "$SCRIPT_DIR/scripts/"
        fi
    done
    
    # Move documentation files to docs directory
    if [ -f "$SCRIPT_DIR/skyscope_design.md" ]; then
        log "DEBUG" "Moving skyscope_design.md to docs/"
        mv "$SCRIPT_DIR/skyscope_design.md" "$SCRIPT_DIR/docs/"
    fi
    
    log "INFO" "Source files organized"
}

# Function to display help
show_help() {
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${CYAN}   Skyscope macOS Patcher Cleanup Script   ${NC}"
    echo -e "${CYAN}==========================================${NC}"
    echo
    echo -e "${GREEN}Usage:${NC} $0 [OPTION]"
    echo
    echo -e "${YELLOW}Options:${NC}"
    echo "  --basic      Clean only Python cache and macOS metadata files"
    echo "  --deep       Clean everything, including build artifacts and temp files"
    echo "  --organize   Organize source files into appropriate directories"
    echo "  --all        Perform all cleanup operations (default)"
    echo "  --help       Display this help message"
    echo
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 --basic     # Quick cleanup of cache files"
    echo "  $0 --deep      # Deep cleanup, removing all build artifacts"
    echo "  $0 --organize  # Only organize source files"
    echo "  $0             # Perform all cleanup operations"
    echo
}

# Main function
main() {
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${CYAN}   Skyscope macOS Patcher Cleanup Script   ${NC}"
    echo -e "${CYAN}==========================================${NC}"
    echo
    
    # Initialize log file
    echo "Cleanup started at $(date)" > "$LOG_FILE"
    
    # Check if running as root
    check_not_root
    
    # Parse command line arguments
    local do_basic=false
    local do_deep=false
    local do_organize=false
    
    if [ $# -eq 0 ]; then
        # Default: do everything
        do_basic=true
        do_deep=true
        do_organize=true
    else
        case "$1" in
            --basic)
                do_basic=true
                ;;
            --deep)
                do_basic=true
                do_deep=true
                ;;
            --organize)
                do_organize=true
                ;;
            --all)
                do_basic=true
                do_deep=true
                do_organize=true
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log "ERROR" "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    fi
    
    # Total steps for progress tracking
    local total_steps=0
    local current_step=0
    
    # Count steps based on selected options
    if [ "$do_basic" = true ]; then
        total_steps=$((total_steps + 2))  # Python cache + macOS metadata
    fi
    if [ "$do_deep" = true ]; then
        total_steps=$((total_steps + 2))  # Build artifacts + temp files
    fi
    if [ "$do_organize" = true ]; then
        total_steps=$((total_steps + 1))  # Organize source files
    fi
    
    # Perform selected cleanup operations
    if [ "$do_basic" = true ]; then
        current_step=$((current_step + 1))
        show_progress $current_step $total_steps "Cleaning Python cache files..."
        clean_python_cache
        
        current_step=$((current_step + 1))
        show_progress $current_step $total_steps "Cleaning macOS metadata files..."
        clean_macos_metadata
    fi
    
    if [ "$do_deep" = true ]; then
        current_step=$((current_step + 1))
        show_progress $current_step $total_steps "Cleaning build artifacts..."
        clean_build_artifacts
        
        current_step=$((current_step + 1))
        show_progress $current_step $total_steps "Cleaning temporary files..."
        clean_temp_files
    fi
    
    if [ "$do_organize" = true ]; then
        current_step=$((current_step + 1))
        show_progress $current_step $total_steps "Organizing source files..."
        organize_source_files
    fi
    
    echo
    echo -e "${GREEN}Cleanup completed successfully!${NC}"
    echo -e "Log file: ${YELLOW}$LOG_FILE${NC}"
    echo
    
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${GREEN}Repository cleanup completed!${NC}"
    echo -e "${CYAN}==========================================${NC}"
}

# Run main function with arguments
main "$@"
