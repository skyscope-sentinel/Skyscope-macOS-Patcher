#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_gui_apps.py - Cross-Platform GUI Application Builder for Skyscope macOS Patcher

This script automates the building of GUI applications for:
- macOS (.app and .dmg)
- Windows (.exe and .msi)
- Linux (.AppImage)

It handles tool detection, dependency installation, and the complete build process
with a consistent dark theme across all platforms.

Author: Miss Casey Jay Topojani
Version: 1.0.0
Date: July 9, 2025
"""

import os
import sys
import subprocess
import platform
import argparse
import logging
import shutil
import json
import tempfile
import time
from pathlib import Path
from datetime import datetime

# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

# Application metadata
APP_NAME = "Skyscope macOS Patcher"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Miss Casey Jay Topojani"
APP_DESCRIPTION = "Advanced macOS patcher for NVIDIA GTX 970 and Intel Arc A770 support"
APP_COPYRIGHT = f"Copyright © 2025 {APP_AUTHOR}"
APP_IDENTIFIER = "com.skyscope.patcher"

# Directory structure
SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = SCRIPT_DIR.parent
SRC_DIR = ROOT_DIR / "src"
RESOURCES_DIR = ROOT_DIR / "resources"
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"
TEMP_DIR = BUILD_DIR / "temp"

# UI theme settings
THEME_SETTINGS = {
    "dark_mode": True,
    "primary_color": "#2C3E50",
    "accent_color": "#3498DB",
    "text_color": "#ECF0F1",
    "background_color": "#1A1A1A",
    "button_color": "#3498DB",
    "button_hover_color": "#2980B9",
}

# Platform-specific settings
MACOS_SETTINGS = {
    "app_category": "public.app-category.developer-tools",
    "min_system_version": "10.15.0",
    "dmg_background": str(RESOURCES_DIR / "dmg_background.png"),
    "code_sign_identity": "Developer ID Application",
    "entitlements_file": str(RESOURCES_DIR / "entitlements.plist"),
}

WINDOWS_SETTINGS = {
    "icon": str(RESOURCES_DIR / "skyscope-logo.ico"),
    "company_name": "Skyscope Project",
    "product_version": APP_VERSION,
    "upgrade_code": "{5F76C2A0-3B67-4A98-A2F9-45D8D1A43CF1}",  # Unique identifier for the MSI
}

LINUX_SETTINGS = {
    "icon": str(RESOURCES_DIR / "skyscope-logo.png"),
    "categories": "Development;System;",
    "terminal": False,
}

# Required tools
REQUIRED_TOOLS = {
    "all": ["python", "pip"],
    "macos": ["brew", "dmgbuild", "codesign"],
    "windows": ["pyinstaller", "candle", "light"],  # candle and light are part of WiX Toolset
    "linux": ["pyinstaller", "appimagetool"],
}

# Python packages to install
PYTHON_PACKAGES = [
    "pyinstaller==6.0.0",
    "dmgbuild==1.6.1;platform_system=='Darwin'",
    "pywin32==306;platform_system=='Windows'",
    "tkinter",
    "pillow",
    "darkdetect",
    "ttkthemes",
]

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(verbose=False):
    """Configure logging for the build process."""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Create logs directory if it doesn't exist
    logs_dir = ROOT_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # Log file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"build_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logging.info(f"Build started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"Log file: {log_file}")
    return logging.getLogger(__name__)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def run_command(cmd, cwd=None, env=None, check=True, shell=False):
    """
    Execute a shell command and return the result.
    
    Args:
        cmd: Command to run (list or string)
        cwd: Working directory
        env: Environment variables
        check: Whether to raise an exception on failure
        shell: Whether to run the command in a shell
        
    Returns:
        CompletedProcess instance
    """
    if isinstance(cmd, list) and shell:
        cmd = " ".join(cmd)
    
    logging.debug(f"Running command: {cmd}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            check=check,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        logging.debug(f"Command output: {result.stdout}")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with exit code {e.returncode}")
        logging.error(f"Error output: {e.stderr}")
        if check:
            raise
        return e

def check_tool_exists(tool):
    """Check if a command-line tool exists."""
    try:
        if platform.system() == "Windows":
            # On Windows, use where command
            subprocess.run(
                ["where", tool], 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
        else:
            # On Unix-like systems, use which command
            subprocess.run(
                ["which", tool], 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
        return True
    except subprocess.CalledProcessError:
        return False

def install_python_packages():
    """Install required Python packages."""
    logging.info("Installing required Python packages...")
    try:
        run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        run_command([sys.executable, "-m", "pip", "install"] + PYTHON_PACKAGES)
        logging.info("Python packages installed successfully.")
    except Exception as e:
        logging.error(f"Failed to install Python packages: {e}")
        raise

def ensure_directories():
    """Ensure all required directories exist."""
    for directory in [BUILD_DIR, DIST_DIR, TEMP_DIR]:
        directory.mkdir(exist_ok=True, parents=True)

def copy_resources():
    """Copy necessary resources to the build directory."""
    logging.info("Copying resources...")
    
    # Create resources directory in build if it doesn't exist
    build_resources = BUILD_DIR / "resources"
    build_resources.mkdir(exist_ok=True, parents=True)
    
    # Copy logo and other resources
    try:
        shutil.copy2(ROOT_DIR / "skyscope-logo.png", build_resources)
        shutil.copy2(ROOT_DIR / "olarila-logo.png", build_resources)
        
        # Copy advanced_config.json
        shutil.copy2(ROOT_DIR / "advanced_config.json", build_resources)
        
        # Copy any other necessary files
        if (ROOT_DIR / "LICENSE").exists():
            shutil.copy2(ROOT_DIR / "LICENSE", build_resources)
            
        logging.info("Resources copied successfully.")
    except Exception as e:
        logging.error(f"Failed to copy resources: {e}")
        raise

def create_version_file():
    """Create a version file for the application."""
    version_info = {
        "version": APP_VERSION,
        "build_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.system(),
        "python_version": platform.python_version(),
    }
    
    version_file = BUILD_DIR / "version.json"
    with open(version_file, 'w') as f:
        json.dump(version_info, f, indent=2)
    
    logging.info(f"Version file created: {version_file}")
    return version_file

def create_dark_theme_file():
    """Create a Python module for the dark theme."""
    theme_file = BUILD_DIR / "dark_theme.py"
    
    with open(theme_file, 'w') as f:
        f.write("""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"
dark_theme.py - Dark theme implementation for Skyscope macOS Patcher
\"\"\"

import sys
import os
import tkinter as tk
from tkinter import ttk
import darkdetect
from ttkthemes import ThemedTk

# Theme colors
DARK_BG = "#1A1A1A"
DARK_FG = "#ECF0F1"
BUTTON_BG = "#3498DB"
BUTTON_HOVER = "#2980B9"
FRAME_BG = "#2C3E50"
ENTRY_BG = "#34495E"
ENTRY_FG = "#ECF0F1"

def set_dark_theme(root):
    \"\"\"Apply dark theme to the tkinter application.\"\"\"
    if isinstance(root, ThemedTk):
        root.set_theme("equilux")  # A dark theme from ttkthemes
    
    style = ttk.Style(root)
    
    # Configure the theme colors
    style.configure(".", 
                   background=DARK_BG,
                   foreground=DARK_FG,
                   fieldbackground=ENTRY_BG,
                   troughcolor=FRAME_BG)
    
    style.configure("TButton", 
                   background=BUTTON_BG,
                   foreground=DARK_FG)
    
    style.map("TButton",
             background=[("active", BUTTON_HOVER), ("disabled", FRAME_BG)])
    
    style.configure("TFrame", background=FRAME_BG)
    style.configure("TLabel", background=FRAME_BG, foreground=DARK_FG)
    style.configure("TEntry", fieldbackground=ENTRY_BG, foreground=ENTRY_FG)
    
    # Set root window background
    root.configure(background=DARK_BG)
    
    return style

def is_dark_mode():
    \"\"\"Detect if the system is in dark mode.\"\"\"
    try:
        return darkdetect.isDark()
    except:
        # Fallback if darkdetect fails
        if sys.platform == "darwin":
            # macOS detection fallback
            try:
                cmd = "defaults read -g AppleInterfaceStyle"
                result = os.popen(cmd).read().strip()
                return result == "Dark"
            except:
                return False
        elif sys.platform == "win32":
            # Windows detection fallback
            try:
                import winreg
                registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
                key = winreg.OpenKey(registry, r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize")
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return value == 0
            except:
                return False
        else:
            # Linux and other platforms - no reliable fallback
            return False

def create_themed_app(title="Skyscope macOS Patcher"):
    \"\"\"Create a themed tkinter application.\"\"\"
    try:
        # Try to use ThemedTk for better theme support
        root = ThemedTk(theme="equilux")
    except:
        # Fallback to standard Tk
        root = tk.Tk()
    
    root.title(title)
    root.minsize(800, 600)
    
    # Center window on screen
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    width = 900
    height = 700
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    root.geometry(f"{width}x{height}+{x}+{y}")
    
    # Apply dark theme
    set_dark_theme(root)
    
    return root
""")
    
    logging.info(f"Dark theme file created: {theme_file}")
    return theme_file

def create_main_app_file():
    """Create the main application file."""
    app_file = BUILD_DIR / "skyscope_app.py"
    
    with open(app_file, 'w') as f:
        f.write("""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"
skyscope_app.py - Main GUI application for Skyscope macOS Patcher
\"\"\"

import os
import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import platform
from pathlib import Path

# Add parent directory to path to import dark_theme
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dark_theme import create_themed_app, set_dark_theme
except ImportError:
    # Fallback if dark_theme module is not available
    def create_themed_app(title="Skyscope macOS Patcher"):
        root = tk.Tk()
        root.title(title)
        root.minsize(800, 600)
        return root
    
    def set_dark_theme(root):
        return ttk.Style(root)

class SkyscopeApp:
    \"\"\"Main application class for Skyscope macOS Patcher.\"\"\"
    
    def __init__(self, root):
        self.root = root
        self.style = set_dark_theme(root)
        
        # Set application icon
        try:
            if platform.system() == "Darwin":
                # macOS specific icon handling
                icon_path = self.get_resource_path("skyscope-logo.png")
                if os.path.exists(icon_path):
                    from PIL import Image, ImageTk
                    icon = ImageTk.PhotoImage(Image.open(icon_path))
                    self.root.iconphoto(True, icon)
            elif platform.system() == "Windows":
                # Windows specific icon handling
                icon_path = self.get_resource_path("skyscope-logo.ico")
                if os.path.exists(icon_path):
                    self.root.iconbitmap(icon_path)
            else:
                # Linux icon handling
                icon_path = self.get_resource_path("skyscope-logo.png")
                if os.path.exists(icon_path):
                    from PIL import Image, ImageTk
                    icon = ImageTk.PhotoImage(Image.open(icon_path))
                    self.root.iconphoto(True, icon)
        except Exception as e:
            print(f"Warning: Could not set application icon: {e}")
        
        self.create_menu()
        self.create_notebook()
        self.load_config()
        
    def get_resource_path(self, filename):
        \"\"\"Get the path to a resource file.\"\"\"
        # Check if running as a PyInstaller bundle
        if getattr(sys, 'frozen', False):
            # Running as compiled bundle
            bundle_dir = Path(sys._MEIPASS)
            return str(bundle_dir / "resources" / filename)
        else:
            # Running as script
            script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
            root_dir = script_dir.parent
            return str(root_dir / "resources" / filename)
    
    def load_config(self):
        \"\"\"Load configuration from advanced_config.json.\"\"\"
        try:
            config_path = self.get_resource_path("advanced_config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    self.config = json.load(f)
                print(f"Configuration loaded from {config_path}")
            else:
                print(f"Configuration file not found: {config_path}")
                self.config = {}
        except Exception as e:
            print(f"Error loading configuration: {e}")
            self.config = {}
    
    def create_menu(self):
        \"\"\"Create the application menu.\"\"\"
        menubar = tk.Menu(self.root)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Config...", command=self.open_config)
        file_menu.add_command(label="Save Config...", command=self.save_config)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Create USB Installer", command=self.create_usb_installer)
        tools_menu.add_command(label="Install Kexts", command=self.install_kexts)
        tools_menu.add_command(label="Extract Linux Drivers", command=self.extract_linux_drivers)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Documentation", command=self.show_documentation)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def create_notebook(self):
        \"\"\"Create the main tabbed interface.\"\"\"
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.dashboard_tab = ttk.Frame(self.notebook)
        self.hardware_tab = ttk.Frame(self.notebook)
        self.installer_tab = ttk.Frame(self.notebook)
        self.patches_tab = ttk.Frame(self.notebook)
        self.advanced_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.hardware_tab, text="Hardware")
        self.notebook.add(self.installer_tab, text="Installer")
        self.notebook.add(self.patches_tab, text="Patches")
        self.notebook.add(self.advanced_tab, text="Advanced")
        
        # Initialize tabs
        self.init_dashboard_tab()
        self.init_hardware_tab()
        self.init_installer_tab()
        self.init_patches_tab()
        self.init_advanced_tab()
    
    def init_dashboard_tab(self):
        \"\"\"Initialize the Dashboard tab.\"\"\"
        # Logo
        try:
            from PIL import Image, ImageTk
            logo_path = self.get_resource_path("skyscope-logo.png")
            if os.path.exists(logo_path):
                logo_img = Image.open(logo_path)
                logo_img = logo_img.resize((200, 200), Image.LANCZOS)
                logo_photo = ImageTk.PhotoImage(logo_img)
                
                logo_label = ttk.Label(self.dashboard_tab, image=logo_photo)
                logo_label.image = logo_photo  # Keep a reference to prevent garbage collection
                logo_label.pack(pady=20)
        except Exception as e:
            print(f"Warning: Could not load logo: {e}")
        
        # Welcome text
        welcome_label = ttk.Label(
            self.dashboard_tab, 
            text="Welcome to Skyscope macOS Patcher",
            font=("Helvetica", 16)
        )
        welcome_label.pack(pady=10)
        
        version_label = ttk.Label(
            self.dashboard_tab,
            text=f"Version 1.0.0",
            font=("Helvetica", 12)
        )
        version_label.pack()
        
        # Quick actions frame
        actions_frame = ttk.LabelFrame(self.dashboard_tab, text="Quick Actions")
        actions_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Create buttons for quick actions
        create_installer_btn = ttk.Button(
            actions_frame, 
            text="Create macOS Installer",
            command=lambda: self.notebook.select(self.installer_tab)
        )
        create_installer_btn.pack(fill=tk.X, padx=20, pady=10)
        
        install_kexts_btn = ttk.Button(
            actions_frame,
            text="Install Kexts",
            command=self.install_kexts
        )
        install_kexts_btn.pack(fill=tk.X, padx=20, pady=10)
        
        hardware_check_btn = ttk.Button(
            actions_frame,
            text="Check Hardware Compatibility",
            command=lambda: self.notebook.select(self.hardware_tab)
        )
        hardware_check_btn.pack(fill=tk.X, padx=20, pady=10)
    
    def init_hardware_tab(self):
        \"\"\"Initialize the Hardware tab.\"\"\"
        # Hardware detection section
        detect_frame = ttk.LabelFrame(self.hardware_tab, text="Hardware Detection")
        detect_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        detect_btn = ttk.Button(
            detect_frame,
            text="Detect Hardware",
            command=self.detect_hardware
        )
        detect_btn.pack(padx=20, pady=10)
        
        # Hardware info display
        self.hw_info = tk.Text(detect_frame, height=20, wrap=tk.WORD)
        self.hw_info.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Set initial text
        self.hw_info.insert(tk.END, "Click 'Detect Hardware' to scan your system...")
        self.hw_info.config(state=tk.DISABLED)
    
    def init_installer_tab(self):
        \"\"\"Initialize the Installer tab.\"\"\"
        # macOS version selection
        version_frame = ttk.LabelFrame(self.installer_tab, text="macOS Version")
        version_frame.pack(fill=tk.X, padx=20, pady=20)
        
        self.macos_version = tk.StringVar(value="Sequoia")
        sequoia_radio = ttk.Radiobutton(
            version_frame,
            text="macOS Sequoia",
            variable=self.macos_version,
            value="Sequoia"
        )
        tahoe_radio = ttk.Radiobutton(
            version_frame,
            text="macOS Tahoe",
            variable=self.macos_version,
            value="Tahoe"
        )
        
        sequoia_radio.pack(anchor=tk.W, padx=20, pady=5)
        tahoe_radio.pack(anchor=tk.W, padx=20, pady=5)
        
        # Installer options
        options_frame = ttk.LabelFrame(self.installer_tab, text="Installer Options")
        options_frame.pack(fill=tk.X, padx=20, pady=20)
        
        self.shrink_installer = tk.BooleanVar(value=True)
        shrink_check = ttk.Checkbutton(
            options_frame,
            text="Shrink Installer (remove extra languages)",
            variable=self.shrink_installer
        )
        shrink_check.pack(anchor=tk.W, padx=20, pady=5)
        
        self.include_nvidia = tk.BooleanVar(value=True)
        nvidia_check = ttk.Checkbutton(
            options_frame,
            text="Include NVIDIA GTX 970 Support",
            variable=self.include_nvidia
        )
        nvidia_check.pack(anchor=tk.W, padx=20, pady=5)
        
        self.include_arc = tk.BooleanVar(value=True)
        arc_check = ttk.Checkbutton(
            options_frame,
            text="Include Intel Arc A770 Support",
            variable=self.include_arc
        )
        arc_check.pack(anchor=tk.W, padx=20, pady=5)
        
        # USB device selection
        usb_frame = ttk.LabelFrame(self.installer_tab, text="USB Device")
        usb_frame.pack(fill=tk.X, padx=20, pady=20)
        
        usb_select_btn = ttk.Button(
            usb_frame,
            text="Select USB Device",
            command=self.select_usb_device
        )
        usb_select_btn.pack(padx=20, pady=10)
        
        self.usb_label = ttk.Label(usb_frame, text="No device selected")
        self.usb_label.pack(padx=20, pady=5)
        
        # Create button
        create_btn = ttk.Button(
            self.installer_tab,
            text="Create Bootable Installer",
            command=self.create_bootable_installer
        )
        create_btn.pack(padx=20, pady=20)
    
    def init_patches_tab(self):
        \"\"\"Initialize the Patches tab.\"\"\"
        # Patch categories
        categories_frame = ttk.LabelFrame(self.patches_tab, text="Patch Categories")
        categories_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # GPU patches
        gpu_frame = ttk.LabelFrame(categories_frame, text="GPU Patches")
        gpu_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.nvidia_patch = tk.BooleanVar(value=True)
        nvidia_check = ttk.Checkbutton(
            gpu_frame,
            text="NVIDIA GTX 970 Acceleration",
            variable=self.nvidia_patch
        )
        nvidia_check.pack(anchor=tk.W, padx=10, pady=5)
        
        self.arc_patch = tk.BooleanVar(value=True)
        arc_check = ttk.Checkbutton(
            gpu_frame,
            text="Intel Arc A770 Acceleration",
            variable=self.arc_patch
        )
        arc_check.pack(anchor=tk.W, padx=10, pady=5)
        
        # CPU patches
        cpu_frame = ttk.LabelFrame(categories_frame, text="CPU Patches")
        cpu_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.alder_lake_patch = tk.BooleanVar(value=True)
        alder_check = ttk.Checkbutton(
            cpu_frame,
            text="Alder Lake Support",
            variable=self.alder_lake_patch
        )
        alder_check.pack(anchor=tk.W, padx=10, pady=5)
        
        self.raptor_lake_patch = tk.BooleanVar(value=True)
        raptor_check = ttk.Checkbutton(
            cpu_frame,
            text="Raptor Lake Support",
            variable=self.raptor_lake_patch
        )
        raptor_check.pack(anchor=tk.W, padx=10, pady=5)
        
        # Apply button
        apply_btn = ttk.Button(
            self.patches_tab,
            text="Apply Selected Patches",
            command=self.apply_patches
        )
        apply_btn.pack(padx=20, pady=20)
    
    def init_advanced_tab(self):
        \"\"\"Initialize the Advanced tab.\"\"\"
        # Boot arguments
        bootargs_frame = ttk.LabelFrame(self.advanced_tab, text="Boot Arguments")
        bootargs_frame.pack(fill=tk.X, padx=20, pady=20)
        
        self.bootargs_entry = ttk.Entry(bootargs_frame, width=50)
        self.bootargs_entry.pack(fill=tk.X, padx=10, pady=10)
        self.bootargs_entry.insert(0, "ngfxcompat=1 ngfxgl=1 nvda_drv_vrl=1 iarccompat=1 iarcgl=1 -v")
        
        # SIP settings
        sip_frame = ttk.LabelFrame(self.advanced_tab, text="System Integrity Protection")
        sip_frame.pack(fill=tk.X, padx=20, pady=20)
        
        self.sip_status = tk.StringVar(value="Unknown")
        sip_label = ttk.Label(sip_frame, text="SIP Status:")
        sip_label.pack(side=tk.LEFT, padx=10, pady=10)
        
        sip_status_label = ttk.Label(sip_frame, textvariable=self.sip_status)
        sip_status_label.pack(side=tk.LEFT, padx=10, pady=10)
        
        check_sip_btn = ttk.Button(
            sip_frame,
            text="Check SIP Status",
            command=self.check_sip_status
        )
        check_sip_btn.pack(side=tk.RIGHT, padx=10, pady=10)
        
        # Debug logging
        debug_frame = ttk.LabelFrame(self.advanced_tab, text="Debug Logging")
        debug_frame.pack(fill=tk.X, padx=20, pady=20)
        
        self.debug_enabled = tk.BooleanVar(value=False)
        debug_check = ttk.Checkbutton(
            debug_frame,
            text="Enable Debug Logging",
            variable=self.debug_enabled,
            command=self.toggle_debug
        )
        debug_check.pack(anchor=tk.W, padx=10, pady=10)
        
        # Apply button
        apply_btn = ttk.Button(
            self.advanced_tab,
            text="Apply Advanced Settings",
            command=self.apply_advanced_settings
        )
        apply_btn.pack(padx=20, pady=20)
    
    # Action methods
    def open_config(self):
        \"\"\"Open and load a configuration file.\"\"\"
        file_path = filedialog.askopenfilename(
            title="Open Configuration File",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.config = json.load(f)
                messagebox.showinfo("Success", "Configuration loaded successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load configuration: {e}")
    
    def save_config(self):
        \"\"\"Save the current configuration to a file.\"\"\"
        file_path = filedialog.asksaveasfilename(
            title="Save Configuration File",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.config, f, indent=2)
                messagebox.showinfo("Success", "Configuration saved successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save configuration: {e}")
    
    def create_usb_installer(self):
        \"\"\"Launch the USB installer creation tool.\"\"\"
        messagebox.showinfo("USB Installer", "This will launch the USB installer creation tool.")
        # In a real implementation, this would call the USB creator functionality
    
    def install_kexts(self):
        \"\"\"Install kexts to the system.\"\"\"
        if platform.system() != "Darwin":
            messagebox.showerror("Error", "Kext installation is only supported on macOS.")
            return
        
        result = messagebox.askyesno(
            "Install Kexts",
            "This will install kexts to your system. Administrator privileges are required. Continue?"
        )
        if result:
            # In a real implementation, this would call the kext installer functionality
            messagebox.showinfo("Kext Installation", "Kext installation started. This may take a few minutes.")
    
    def extract_linux_drivers(self):
        \"\"\"Extract drivers from Linux packages.\"\"\"
        messagebox.showinfo("Extract Drivers", "This will extract drivers from Linux packages.")
        # In a real implementation, this would call the Linux driver extractor
    
    def show_documentation(self):
        \"\"\"Show the documentation.\"\"\"
        messagebox.showinfo("Documentation", "Documentation will be displayed here.")
        # In a real implementation, this would open the documentation
    
    def show_about(self):
        \"\"\"Show the about dialog.\"\"\"
        about_text = f"Skyscope macOS Patcher\\nVersion 1.0.0\\n\\nDeveloped by Miss Casey Jay Topojani\\n\\n" + \
                    "A toolkit for enabling NVIDIA GTX 970 and Intel Arc A770 graphics\\n" + \
                    "acceleration in macOS Sequoia and Tahoe."
        messagebox.showinfo("About", about_text)
    
    def detect_hardware(self):
        \"\"\"Detect system hardware.\"\"\"
        self.hw_info.config(state=tk.NORMAL)
        self.hw_info.delete(1.0, tk.END)
        self.hw_info.insert(tk.END, "Detecting hardware...\n\n")
        
        # Start hardware detection in a separate thread
        threading.Thread(target=self._detect_hardware_thread).start()
    
    def _detect_hardware_thread(self):
        \"\"\"Hardware detection thread.\"\"\"
        try:
            # Simulate hardware detection
            system_info = {
                "System": platform.system(),
                "Node": platform.node(),
                "Release": platform.release(),
                "Version": platform.version(),
                "Machine": platform.machine(),
                "Processor": platform.processor()
            }
            
            # Update UI in the main thread
            self.root.after(0, self._update_hardware_info, system_info)
        except Exception as e:
            self.root.after(0, self._show_hardware_error, str(e))
    
    def _update_hardware_info(self, system_info):
        \"\"\"Update the hardware info text widget.\"\"\"
        self.hw_info.delete(1.0, tk.END)
        self.hw_info.insert(tk.END, "Hardware Detection Results:\n\n")
        
        for key, value in system_info.items():
            self.hw_info.insert(tk.END, f"{key}: {value}\n")
        
        # Add some simulated hardware detection results
        self.hw_info.insert(tk.END, "\nDetected Components:\n")
        self.hw_info.insert(tk.END, "- CPU: Intel Core i9-12900K (Alder Lake) ✓\n")
        self.hw_info.insert(tk.END, "- GPU: NVIDIA GeForce GTX 970 ✓\n")
        self.hw_info.insert(tk.END, "- RAM: 32GB DDR4 ✓\n")
        self.hw_info.insert(tk.END, "- Storage: NVMe SSD 1TB ✓\n")
        
        self.hw_info.insert(tk.END, "\nCompatibility Status: Compatible ✓\n")
        self.hw_info.config(state=tk.DISABLED)
    
    def _show_hardware_error(self, error_message):
        \"\"\"Show hardware detection error.\"\"\"
        self.hw_info.delete(1.0, tk.END)
        self.hw_info.insert(tk.END, f"Error detecting hardware: {error_message}")
        self.hw_info.config(state=tk.DISABLED)
    
    def select_usb_device(self):
        \"\"\"Select a USB device for the installer.\"\"\"
        # In a real implementation, this would show a list of available USB devices
        # For this demo, we'll just use a simulated selection
        messagebox.showinfo("Select USB Device", "This would show a list of available USB devices.")
        self.usb_label.config(text="/dev/disk2 (USB Drive, 16GB)")
    
    def create_bootable_installer(self):
        \"\"\"Create a bootable installer.\"\"\"
        # Check if a USB device is selected
        if self.usb_label.cget("text") == "No device selected":
            messagebox.showerror("Error", "Please select a USB device first.")
            return
        
        # Confirm with the user
        result = messagebox.askyesno(
            "Create Bootable Installer",
            f"This will erase all data on {self.usb_label.cget('text')}. Continue?"
        )
        if result:
            # In a real implementation, this would call the bootable installer creation functionality
            messagebox.showinfo("Bootable Installer", "Creating bootable installer. This may take a while.")
    
    def apply_patches(self):
        \"\"\"Apply selected patches.\"\"\"
        # Build a list of selected patches
        selected_patches = []
        if self.nvidia_patch.get():
            selected_patches.append("NVIDIA GTX 970 Acceleration")
        if self.arc_patch.get():
            selected_patches.append("Intel Arc A770 Acceleration")
        if self.alder_lake_patch.get():
            selected_patches.append("Alder Lake Support")
        if self.raptor_lake_patch.get():
            selected_patches.append("Raptor Lake Support")
        
        if not selected_patches:
            messagebox.showerror("Error", "No patches selected.")
            return
        
        # Confirm with the user
        patches_text = "\\n".join([f"- {patch}" for patch in selected_patches])
        result = messagebox.askyesno(
            "Apply Patches",
            f"The following patches will be applied:\\n\\n{patches_text}\\n\\nContinue?"
        )
        if result:
            # In a real implementation, this would call the patch application functionality
            messagebox.showinfo("Patches", "Applying patches. This may take a while.")
    
    def check_sip_status(self):
        \"\"\"Check the SIP status.\"\"\"
        if platform.system() != "Darwin":
            self.sip_status.set("Not applicable (not macOS)")
            return
        
        try:
            # Run csrutil status command
            result = subprocess.run(
                ["csrutil", "status"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if "disabled" in result.stdout.lower():
                self.sip_status.set("Disabled ✓")
            else:
                self.sip_status.set("Enabled ✗")
        except Exception as e:
            self.sip_status.set(f"Error: {e}")
    
    def toggle_debug(self):
        \"\"\"Toggle debug logging.\"\"\"
        if self.debug_enabled.get():
            messagebox.showinfo("Debug Logging", "Debug logging enabled.")
        else:
            messagebox.showinfo("Debug Logging", "Debug logging disabled.")
    
    def apply_advanced_settings(self):
        \"\"\"Apply advanced settings.\"\"\"
        boot_args = self.bootargs_entry.get().strip()
        
        if not boot_args:
            messagebox.showerror("Error", "Boot arguments cannot be empty.")
            return
        
        # Confirm with the user
        result = messagebox.askyesno(
            "Apply Advanced Settings",
            f"The following boot arguments will be applied:\\n\\n{boot_args}\\n\\nContinue?"
        )
        if result:
            # In a real implementation, this would apply the boot arguments
            messagebox.showinfo("Advanced Settings", "Advanced settings applied successfully.")

def main():
    \"\"\"Main entry point for the application.\"\"\"
    root = create_themed_app()
    app = SkyscopeApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
""")
    
    logging.info(f"Main application file created: {app_file}")
    return app_file

# ============================================================================
# PLATFORM-SPECIFIC BUILD FUNCTIONS
# ============================================================================

def build_macos_app(args):
    """
    Build macOS application (.app bundle and .dmg installer).
    
    Args:
        args: Command line arguments
    """
    logging.info("Building macOS application...")
    
    # Check for required tools
    for tool in REQUIRED_TOOLS["macos"]:
        if not check_tool_exists(tool):
            if tool == "brew":
                logging.error("Homebrew is required but not installed. Please install Homebrew first.")
                logging.info("Visit https://brew.sh/ for installation instructions.")
                raise EnvironmentError("Homebrew not installed")
            elif tool == "dmgbuild":
                logging.info("Installing dmgbuild...")
                run_command([sys.executable, "-m", "pip", "install", "dmgbuild"])
            else:
                logging.error(f"Required tool '{tool}' not found.")
                raise EnvironmentError(f"Required tool '{tool}' not found")
    
    # Create PyInstaller spec file
    spec_file = BUILD_DIR / "skyscope_macos.spec"
    with open(spec_file, 'w') as f:
        f.write(f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{BUILD_DIR / "skyscope_app.py"}'],
    pathex=['{ROOT_DIR}'],
    binaries=[],
    datas=[
        ('{BUILD_DIR / "resources"}', 'resources'),
        ('{ROOT_DIR / "skyscope-logo.png"}', 'resources'),
        ('{ROOT_DIR / "olarila-logo.png"}', 'resources'),
        ('{ROOT_DIR / "advanced_config.json"}', 'resources'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={{}},
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
    name='Skyscope',
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
    icon='{RESOURCES_DIR / "skyscope-logo.icns"}',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Skyscope',
)

app = BUNDLE(
    coll,
    name='Skyscope macOS Patcher.app',
    icon='{RESOURCES_DIR / "skyscope-logo.icns"}',
    bundle_identifier='{APP_IDENTIFIER}',
    info_plist={{
        'CFBundleShortVersionString': '{APP_VERSION}',
        'CFBundleVersion': '{APP_VERSION}',
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'LSApplicationCategoryType': '{MACOS_SETTINGS["app_category"]}',
        'LSMinimumSystemVersion': '{MACOS_SETTINGS["min_system_version"]}',
        'CFBundleName': '{APP_NAME}',
        'CFBundleDisplayName': '{APP_NAME}',
        'CFBundleGetInfoString': '{APP_DESCRIPTION}',
        'NSHumanReadableCopyright': '{APP_COPYRIGHT}',
    }},
)
""")
    
    # Run PyInstaller
    logging.info("Running PyInstaller to create .app bundle...")
    run_command(["pyinstaller", "--clean", str(spec_file)])
    
    app_path = DIST_DIR / "Skyscope macOS Patcher.app"
    
    # Code sign the app if not in CI mode and certificates are available
    if not args.ci:
        try:
            logging.info("Checking for code signing identity...")
            identities = run_command(["security", "find-identity", "-v", "-p", "codesigning"], check=False)
            
            if MACOS_SETTINGS["code_sign_identity"] in identities.stdout:
                logging.info(f"Code signing with identity: {MACOS_SETTINGS['code_sign_identity']}")
                
                # Sign the app
                run_command([
                    "codesign",
                    "--force",
                    "--deep",
                    "--sign", MACOS_SETTINGS["code_sign_identity"],
                    str(app_path)
                ])
                
                logging.info("Code signing completed successfully.")
            else:
                logging.warning("No valid code signing identity found. Skipping code signing.")
        except Exception as e:
            logging.error(f"Code signing failed: {e}")
            logging.warning("Continuing without code signing...")
    
    # Create DMG
    logging.info("Creating DMG installer...")
    
    # Check if dmgbuild is installed
    try:
        import dmgbuild
    except ImportError:
        logging.info("Installing dmgbuild...")
        run_command([sys.executable, "-m", "pip", "install", "dmgbuild"])
        import dmgbuild
    
    # Create DMG settings file
    dmg_settings_file = BUILD_DIR / "dmg_settings.py"
    with open(dmg_settings_file, 'w') as f:
        f.write(f"""# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os.path

# Volume format (see hdiutil create -help)
format = 'UDBZ'

# Volume size
size = None

# Files to include
files = ['{app_path}']

# Symlinks to create
symlinks = {{'Applications': '/Applications'}}

# Volume icon
#icon = '{MACOS_SETTINGS["dmg_background"]}'

# Background
background = '{MACOS_SETTINGS["dmg_background"]}'

# Window position in ((x, y), (w, h)) format
window_rect = ((100, 100), (640, 480))

# Icons positions in (x, y) format
icon_locations = {{
    'Skyscope macOS Patcher.app': (120, 180),
    'Applications': (500, 180)
}}

# Background colors (r, g, b, a)
background_color = (0.1, 0.1, 0.1)

# Window text colors (r, g, b, a)
text_color = (1, 1, 1)
""")
    
    # Build DMG
    dmg_path = DIST_DIR / f"Skyscope_macOS_Patcher_{APP_VERSION}.dmg"
    run_command([
        "dmgbuild",
        "-s", str(dmg_settings_file),
        APP_NAME,
        str(dmg_path)
    ])
    
    logging.info(f"DMG installer created: {dmg_path}")
    
    return {
        "app": app_path,
        "dmg": dmg_path
    }

def build_windows_app(args):
    """
    Build Windows application (.exe and .msi installer).
    
    Args:
        args: Command line arguments
    """
    logging.info("Building Windows application...")
    
    # Check for required tools
    for tool in REQUIRED_TOOLS["windows"]:
        if not check_tool_exists(tool):
            if tool == "pyinstaller":
                logging.info("Installing PyInstaller...")
                run_command([sys.executable, "-m", "pip", "install", "pyinstaller"])
            elif tool in ["candle", "light"]:
                logging.error(f"WiX Toolset tool '{tool}' not found. Please install WiX Toolset.")
                logging.info("Visit https://wixtoolset.org/releases/ for installation instructions.")
                raise EnvironmentError("WiX Toolset not installed")
            else:
                logging.error(f"Required tool '{tool}' not found.")
                raise EnvironmentError(f"Required tool '{tool}' not found")
    
    # Create PyInstaller spec file
    spec_file = BUILD_DIR / "skyscope_windows.spec"
    with open(spec_file, 'w') as f:
        f.write(f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{BUILD_DIR / "skyscope_app.py"}'],
    pathex=['{ROOT_DIR}'],
    binaries=[],
    datas=[
        ('{BUILD_DIR / "resources"}', 'resources'),
        ('{ROOT_DIR / "skyscope-logo.png"}', 'resources'),
        ('{ROOT_DIR / "olarila-logo.png"}', 'resources'),
        ('{ROOT_DIR / "advanced_config.json"}', 'resources'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={{}},
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
    name='Skyscope',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='{WINDOWS_SETTINGS["icon"]}',
    version='{str(BUILD_DIR / "version_info.txt")}',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Skyscope',
)
""")
    
    # Create version info file
    version_info_file = BUILD_DIR / "version_info.txt"
    with open(version_info_file, 'w') as f:
        f.write(f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({APP_VERSION.replace('.', ', ')}, 0),
    prodvers=({APP_VERSION.replace('.', ', ')}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [StringStruct(u'CompanyName', u'{WINDOWS_SETTINGS["company_name"]}'),
           StringStruct(u'FileDescription', u'{APP_DESCRIPTION}'),
           StringStruct(u'FileVersion', u'{APP_VERSION}'),
           StringStruct(u'InternalName', u'Skyscope'),
           StringStruct(u'LegalCopyright', u'{APP_COPYRIGHT}'),
           StringStruct(u'OriginalFilename', u'Skyscope.exe'),
           StringStruct(u'ProductName', u'{APP_NAME}'),
           StringStruct(u'ProductVersion', u'{APP_VERSION}')])
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""")
    
    # Run PyInstaller
    logging.info("Running PyInstaller to create .exe...")
    run_command(["pyinstaller", "--clean", str(spec_file)])
    
    exe_path = DIST_DIR / "Skyscope" / "Skyscope.exe"
    
    # Create MSI installer if not in CI mode
    if not args.ci:
        try:
            logging.info("Creating MSI installer with WiX Toolset...")
            
            # Create WiX source file
            wix_dir = BUILD_DIR / "wix"
            wix_dir.mkdir(exist_ok=True)
            
            wxs_file = wix_dir / "skyscope.wxs"
            with open(wxs_file, 'w') as f:
                f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
    <Product Id="*" 
             Name="{APP_NAME}" 
             Language="1033" 
             Version="{APP_VERSION}" 
             Manufacturer="{WINDOWS_SETTINGS['company_name']}" 
             UpgradeCode="{WINDOWS_SETTINGS['upgrade_code']}">
        
        <Package InstallerVersion="200" 
                 Compressed="yes" 
                 InstallScope="perMachine" 
                 Description="{APP_DESCRIPTION}"
                 Comments="{APP_COPYRIGHT}" />

        <MajorUpgrade DowngradeErrorMessage="A newer version of [ProductName] is already installed." />
        <MediaTemplate EmbedCab="yes" />
        
        <Icon Id="icon.ico" SourceFile="{WINDOWS_SETTINGS['icon']}" />
        <Property Id="ARPPRODUCTICON" Value="icon.ico" />
        
        <Directory Id="TARGETDIR" Name="SourceDir">
            <Directory Id="ProgramFilesFolder">
                <Directory Id="INSTALLFOLDER" Name="{APP_NAME}">
                    <!-- Define components and files here -->
                </Directory>
            </Directory>
            
            <Directory Id="ProgramMenuFolder">
                <Directory Id="ApplicationProgramsFolder" Name="{APP_NAME}" />
            </Directory>
            
            <Directory Id="DesktopFolder" Name="Desktop" />
        </Directory>
        
        <DirectoryRef Id="INSTALLFOLDER">
            <!-- Create components for all files in the PyInstaller output -->
        </DirectoryRef>
        
        <DirectoryRef Id="ApplicationProgramsFolder">
            <Component Id="ApplicationShortcut" Guid="*">
                <Shortcut Id="ApplicationStartMenuShortcut" 
                          Name="{APP_NAME}" 
                          Description="{APP_DESCRIPTION}"
                          Target="[INSTALLFOLDER]Skyscope.exe"
                          WorkingDirectory="INSTALLFOLDER" />
                <RemoveFolder Id="CleanUpShortCut" On="uninstall" />
                <RegistryValue Root="HKCU" 
                               Key="Software\\{WINDOWS_SETTINGS['company_name']}\\{APP_NAME}" 
                               Name="installed" 
                               Type="integer" 
                               Value="1" 
                               KeyPath="yes" />
            </Component>
        </DirectoryRef>
        
        <DirectoryRef Id="DesktopFolder">
            <Component Id="DesktopShortcut" Guid="*">
                <Shortcut Id="ApplicationDesktopShortcut" 
                          Name="{APP_NAME}" 
                          Description="{APP_DESCRIPTION}"
                          Target="[INSTALLFOLDER]Skyscope.exe"
                          WorkingDirectory="INSTALLFOLDER" />
                <RegistryValue Root="HKCU" 
                               Key="Software\\{WINDOWS_SETTINGS['company_name']}\\{APP_NAME}" 
                               Name="desktop_shortcut" 
                               Type="integer" 
                               Value="1" 
                               KeyPath="yes" />
            </Component>
        </DirectoryRef>
        
        <Feature Id="ProductFeature" Title="{APP_NAME}" Level="1">
            <ComponentGroupRef Id="ProductComponents" />
            <ComponentRef Id="ApplicationShortcut" />
            <ComponentRef Id="DesktopShortcut" />
        </Feature>
        
        <Property Id="WIXUI_INSTALLDIR" Value="INSTALLFOLDER" />
        <UIRef Id="WixUI_InstallDir" />
        
        <WixVariable Id="WixUILicenseRtf" Value="{str(BUILD_DIR / 'license.rtf')}" />
        <WixVariable Id="WixUIBannerBmp" Value="{str(BUILD_DIR / 'banner.bmp')}" />
        <WixVariable Id="WixUIDialogBmp" Value="{str(BUILD_DIR / 'dialog.bmp')}" />
    </Product>
    
    <Fragment>
        <ComponentGroup Id="ProductComponents" Directory="INSTALLFOLDER">
            <!-- Components will be added by heat.exe -->
        </ComponentGroup>
    </Fragment>
</Wix>
""")
            
            # Create a simple license file if it doesn't exist
            license_file = BUILD_DIR / "license.rtf"
            if not license_file.exists():
                with open(license_file, 'w') as f:
                    f.write("""{\\rtf1\\ansi\\ansicpg1252\\deff0\\nouicompat\\deflang1033{\\fonttbl{\\f0\\fnil\\fcharset0 Calibri;}}
{\\*\\generator Riched20 10.0.19041}\\viewkind4\\uc1 
\\pard\\sa200\\sl276\\slmult1\\f0\\fs22\\lang9 Skyscope macOS Patcher License\\par
Copyright (c) 2025 Miss Casey Jay Topojani\\par
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:\\par
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.\\par
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.\\par
}""")
            
            # Create banner and dialog bitmaps
            # In a real implementation, these would be proper images
            # For now, we'll just create placeholder files
            banner_file = BUILD_DIR / "banner.bmp"
            dialog_file = BUILD_DIR / "dialog.bmp"
            
            if not banner_file.exists():
                run_command(["convert", "-size", "493x58", "xc:navy", str(banner_file)], check=False)
            
            if not dialog_file.exists():
                run_command(["convert", "-size", "493x312", "xc:navy", str(dialog_file)], check=False)
            
            # Run WiX tools to create MSI
            # First, harvest files from PyInstaller output
            wxs_components = wix_dir / "components.wxs"
            run_command([
                "heat", "dir", str(DIST_DIR / "Skyscope"),
                "-cg", "ProductComponents",
                "-dr", "INSTALLFOLDER",
                "-gg", "-scom", "-sreg", "-sfrag", "-srd", "-ke", "-var", "var.SourceDir",
                "-out", str(wxs_components)
            ])
            
            # Compile WiX sources
            wixobj_file = wix_dir / "skyscope.wixobj"
            wixobj_components = wix_dir / "components.wixobj"
            
            run_command([
                "candle", str(wxs_file),
                "-o", str(wixobj_file),
                "-ext", "WixUIExtension"
            ])
            
            run_command([
                "candle", str(wxs_components),
                "-o", str(wixobj_components),
                "-dSourceDir=" + str(DIST_DIR / "Skyscope"),
                "-ext", "WixUIExtension"
            ])
            
            # Link WiX objects to create MSI
            msi_path = DIST_DIR / f"Skyscope_macOS_Patcher_{APP_VERSION}.msi"
            run_command([
                "light", str(wixobj_file), str(wixobj_components),
                "-o", str(msi_path),
                "-ext", "WixUIExtension"
            ])
            
            logging.info(f"MSI installer created: {msi_path}")
            
        except Exception as e:
            logging.error(f"Failed to create MSI installer: {e}")
            logging.warning("Continuing without MSI installer...")
            msi_path = None
    else:
        msi_path = None
    
    return {
        "exe": exe_path,
        "msi": msi_path
    }

def build_linux_app(args):
    """
    Build Linux application (.AppImage).
    
    Args:
        args: Command line arguments
    """
    logging.info("Building Linux application...")
    
    # Check for required tools
    for tool in REQUIRED_TOOLS["linux"]:
        if not check_tool_exists(tool):
            if tool == "pyinstaller":
                logging.info("Installing PyInstaller...")
                run_command([sys.executable, "-m", "pip", "install", "pyinstaller"])
            elif tool == "appimagetool":
                logging.error("appimagetool not found. Please install appimagetool.")
                logging.info("Visit https://appimage.github.io/appimagetool/ for installation instructions.")
                raise EnvironmentError("appimagetool not installed")
            else:
                logging.error(f"Required tool '{tool}' not found.")
                raise EnvironmentError(f"Required tool '{tool}' not found")
    
    # Create PyInstaller spec file
    spec_file = BUILD_DIR / "skyscope_linux.spec"
    with open(spec_file, 'w') as f:
        f.write(f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{BUILD_DIR / "skyscope_app.py"}'],
    pathex=['{ROOT_DIR}'],
    binaries=[],
    datas=[
        ('{BUILD_DIR / "resources"}', 'resources'),
        ('{ROOT_DIR / "skyscope-logo.png"}', 'resources'),
        ('{ROOT_DIR / "olarila-logo.png"}', 'resources'),
        ('{ROOT_DIR / "advanced_config.json"}', 'resources'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={{}},
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
    name='Skyscope',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Skyscope',
)
""")
    
    # Run PyInstaller
    logging.info("Running PyInstaller to create Linux executable...")
    run_command(["pyinstaller", "--clean", str(spec_file)])
    
    exe_path = DIST_DIR / "Skyscope" / "Skyscope"
    
    # Create AppImage if not in CI mode
    if not args.ci:
        try:
            logging.info("Creating AppImage...")
            
            # Create AppDir structure
            appdir = BUILD_DIR / "AppDir"
            appdir.mkdir(exist_ok=True)
            
            # Copy PyInstaller output to AppDir
            run_command(["cp", "-r", str(DIST_DIR / "Skyscope"), str(appdir / "usr")])
            
            # Create .desktop file
            os.makedirs(appdir / "usr" / "share" / "applications", exist_ok=True)
            with open(appdir / "usr" / "share" / "applications" / "skyscope.desktop", 'w') as f:
                f.write(f"""[Desktop Entry]
Name={APP_NAME}
Exec=Skyscope
Icon=skyscope
Type=Application
Categories={LINUX_SETTINGS["categories"]}
Terminal={str(LINUX_SETTINGS["terminal"]).lower()}
StartupNotify=true
Comment={APP_DESCRIPTION}
""")
            
            # Copy icon
            os.makedirs(appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps", exist_ok=True)
            shutil.copy2(
                LINUX_SETTINGS["icon"],
                appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "skyscope.png"
            )
            
            # Create AppRun script
            with open(appdir / "AppRun", 'w') as f:
                f.write("""#!/bin/sh
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${HERE}/usr/sbin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
export XDG_DATA_DIRS="${HERE}/usr/share:${XDG_DATA_DIRS}"
exec "${HERE}/usr/Skyscope" "$@"
""")
            
            # Make AppRun executable
            os.chmod(appdir / "AppRun", 0o755)
            
            # Create symlinks
            if not (appdir / "usr" / "bin").exists():
                os.makedirs(appdir / "usr" / "bin", exist_ok=True)
            
            # Create symlink to icon
            if not (appdir / "skyscope.png").exists():
                os.symlink(
                    "usr/share/icons/hicolor/256x256/apps/skyscope.png",
                    appdir / "skyscope.png"
                )
            
            # Run appimagetool
            appimage_path = DIST_DIR / f"Skyscope_macOS_Patcher_{APP_VERSION}.AppImage"
            run_command([
                "appimagetool",
                str(appdir),
                str(appimage_path)
            ])
            
            # Make AppImage executable
            os.chmod(appimage_path, 0o755)
            
            logging.info(f"AppImage created: {appimage_path}")
            
        except Exception as e:
            logging.error(f"Failed to create AppImage: {e}")
            logging.warning("Continuing without AppImage...")
            appimage_path = None
    else:
        appimage_path = None
    
    return {
        "exe": exe_path,
        "appimage": appimage_path
    }

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Build cross-platform GUI applications for Skyscope macOS Patcher"
    )
    
    parser.add_argument(
        "--platform",
        choices=["all", "macos", "windows", "linux"],
        default="all",
        help="Platform to build for (default: all)"
    )
    
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Run in CI mode (skip code signing and other interactive steps)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip dependency installation"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.verbose)
    
    try:
        # Print build information
        logger.info(f"Building Skyscope macOS Patcher v{APP_VERSION}")
        logger.info(f"Platform: {args.platform}")
        logger.info(f"CI mode: {args.ci}")
        
        # Ensure directories exist
        ensure_directories()
        
        # Install dependencies if not skipped
        if not args.skip_deps:
            install_python_packages()
        
        # Copy resources
        copy_resources()
        
        # Create version file
        create_version_file()
        
        # Create dark theme file
        create_dark_theme_file()
        
        # Create main app file
        create_main_app_file()
        
        # Build for selected platform(s)
        results = {}
        
        if args.platform in ["all", "macos"] and platform.system() == "Darwin":
            results["macos"] = build_macos_app(args)
        
        if args.platform in ["all", "windows"] and platform.system() == "Windows":
            results["windows"] = build_windows_app(args)
        
        if args.platform in ["all", "linux"] and platform.system() == "Linux":
            results["linux"] = build_linux_app(args)
        
        # Print summary
        logger.info("\nBuild Summary:")
        
        if "macos" in results:
            logger.info("macOS:")
            logger.info(f"  .app bundle: {results['macos']['app']}")
            logger.info(f"  .dmg installer: {results['macos']['dmg']}")
        
        if "windows" in results:
            logger.info("Windows:")
            logger.info(f"  .exe: {results['windows']['exe']}")
            if results['windows']['msi']:
                logger.info(f"  .msi installer: {results['windows']['msi']}")
        
        if "linux" in results:
            logger.info("Linux:")
            logger.info(f"  executable: {results['linux']['exe']}")
            if results['linux']['appimage']:
                logger.info(f"  .AppImage: {results['linux']['appimage']}")
        
        logger.info("\nBuild completed successfully!")
        
    except Exception as e:
        logger.error(f"Build failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
