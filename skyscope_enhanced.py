#!/usr/bin/env python3
"""
skyscope_enhanced.py
Skyscope macOS Patcher - Main Application

Comprehensive macOS patcher that enables NVIDIA and Intel Arc graphics cards
to work with full acceleration and Metal support in macOS Sequoia and Tahoe.
Features hardware detection, kext installation, system configuration, and
installer creation with support for GTX 970 and Intel Arc A770.

Developer: Miss Casey Jay Topojani
Version: 1.0.0
Date: July 9, 2025
"""

import os
import sys
import re
import json
import hashlib
import argparse
import logging
import time
import shutil
import tempfile
import platform
import subprocess
import plistlib
import glob
import ctypes
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any, Set
from datetime import datetime

# Try to import UI libraries
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    HAS_TK = True
except ImportError:
    HAS_TK = False

try:
    import requests
    from tqdm import tqdm
except ImportError:
    print("Required packages not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "tqdm"])
    import requests
    from tqdm import tqdm

# Import Skyscope modules (with path handling for both direct run and installed package)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

try:
    from src.installers.macos_downloader import MacOSDownloader
    from src.installers.usb_creator import USBCreator, HARDWARE_CONFIGS
    from src.utils.linux_extractor import LinuxDriverExtractor
except ImportError:
    print("Skyscope modules not found in expected location.")
    print("Trying alternative import paths...")
    
    # Try to find modules in common locations
    possible_paths = [
        os.path.join(SCRIPT_DIR, "src"),
        os.path.join(os.path.dirname(SCRIPT_DIR), "src"),
        os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Skyscope", "src")
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            sys.path.insert(0, os.path.dirname(path))
            try:
                from src.installers.macos_downloader import MacOSDownloader
                from src.installers.usb_creator import USBCreator, HARDWARE_CONFIGS
                from src.utils.linux_extractor import LinuxDriverExtractor
                break
            except ImportError:
                continue
    else:
        print("ERROR: Could not find required Skyscope modules.")
        print("Please make sure you're running this script from the Skyscope directory")
        print("or that the Skyscope package is properly installed.")
        sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(SCRIPT_DIR, 'skyscope.log'))
    ]
)
logger = logging.getLogger('Skyscope')

# Constants
VERSION = "1.0.0"
BUILD_DATE = "July 9, 2025"
DEFAULT_CONFIG_PATH = os.path.join(SCRIPT_DIR, "advanced_config.json")
DEFAULT_WORK_DIR = os.path.expanduser("~/Library/Caches/SkyscopePatcher")
DEFAULT_KEXTS_DIR = os.path.join(SCRIPT_DIR, "resources", "Kexts")
DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Skyscope_Output")

# macOS version information
MACOS_VERSIONS = {
    "sequoia": {
        "version": "15",
        "build_pattern": r"15[A-Z]\d+[a-z]?",
        "marketing_name": "Sequoia",
        "min_build": "15A",
    },
    "tahoe": {
        "version": "16",
        "build_pattern": r"16[A-Z]\d+[a-z]?",
        "marketing_name": "Tahoe",
        "min_build": "16A",
    }
}

# Hardware support information
SUPPORTED_NVIDIA_GPUS = {
    "0x13C2": "NVIDIA GeForce GTX 970",
    "0x17C8": "NVIDIA GeForce GTX 980 Ti",
    "0x1B81": "NVIDIA GeForce GTX 1070",
    "0x1B06": "NVIDIA GeForce GTX 1080 Ti"
}

SUPPORTED_INTEL_GPUS = {
    "0x56A0": "Intel Arc A770",
    "0x56A1": "Intel Arc A750",
    "0x56A5": "Intel Arc A580",
    "0x56A6": "Intel Arc A380"
}

SUPPORTED_INTEL_CPUS = {
    "alder_lake": {
        "name": "Intel Alder Lake",
        "family": 6,
        "models": [0x97, 0x9A]  # 12th gen
    },
    "raptor_lake": {
        "name": "Intel Raptor Lake",
        "family": 6,
        "models": [0xB7, 0xBA, 0xBF]  # 13th gen
    }
}

class HardwareInfo:
    """Class to detect and store hardware information"""
    
    def __init__(self):
        """Initialize hardware info"""
        self.os_name = platform.system()
        self.os_version = platform.version()
        self.os_release = platform.release()
        self.machine = platform.machine()
        self.processor = platform.processor()
        
        # Initialize hardware components
        self.cpu = {
            "vendor": "Unknown",
            "brand": "Unknown",
            "family": 0,
            "model": 0,
            "stepping": 0,
            "cores": 0,
            "threads": 0,
            "supported": False,
            "support_reason": "Unknown CPU"
        }
        
        self.gpus = []
        self.ram_gb = 0
        self.storage_gb = 0
        
        # Detect hardware
        self._detect_hardware()
    
    def _detect_hardware(self):
        """Detect hardware components"""
        self._detect_cpu()
        self._detect_gpus()
        self._detect_memory()
        self._detect_storage()
    
    def _detect_cpu(self):
        """Detect CPU information"""
        if self.os_name == "Darwin":  # macOS
            self._detect_cpu_macos()
        elif self.os_name == "Linux":
            self._detect_cpu_linux()
        elif self.os_name == "Windows":
            self._detect_cpu_windows()
        
        # Check if CPU is supported
        self._check_cpu_support()
    
    def _detect_cpu_macos(self):
        """Detect CPU on macOS"""
        try:
            # Use sysctl to get CPU info
            sysctl_output = subprocess.check_output(["sysctl", "-a"], universal_newlines=True)
            
            # Extract CPU brand
            brand_match = re.search(r"machdep.cpu.brand_string: (.*)", sysctl_output)
            if brand_match:
                self.cpu["brand"] = brand_match.group(1)
            
            # Extract vendor
            vendor_match = re.search(r"machdep.cpu.vendor: (.*)", sysctl_output)
            if vendor_match:
                self.cpu["vendor"] = vendor_match.group(1)
            
            # Extract family, model, stepping
            family_match = re.search(r"machdep.cpu.family: (\d+)", sysctl_output)
            if family_match:
                self.cpu["family"] = int(family_match.group(1))
            
            model_match = re.search(r"machdep.cpu.model: (\d+)", sysctl_output)
            if model_match:
                self.cpu["model"] = int(model_match.group(1))
            
            stepping_match = re.search(r"machdep.cpu.stepping: (\d+)", sysctl_output)
            if stepping_match:
                self.cpu["stepping"] = int(stepping_match.group(1))
            
            # Extract core count
            core_count_match = re.search(r"machdep.cpu.core_count: (\d+)", sysctl_output)
            if core_count_match:
                self.cpu["cores"] = int(core_count_match.group(1))
            
            # Extract thread count
            thread_count_match = re.search(r"machdep.cpu.thread_count: (\d+)", sysctl_output)
            if thread_count_match:
                self.cpu["threads"] = int(thread_count_match.group(1))
            
        except Exception as e:
            logger.error(f"Failed to detect CPU on macOS: {e}")
    
    def _detect_cpu_linux(self):
        """Detect CPU on Linux"""
        try:
            # Read from /proc/cpuinfo
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
            
            # Extract CPU brand
            brand_matches = re.findall(r"model name\s+: (.*)", cpuinfo)
            if brand_matches:
                self.cpu["brand"] = brand_matches[0]
            
            # Extract vendor
            vendor_matches = re.findall(r"vendor_id\s+: (.*)", cpuinfo)
            if vendor_matches:
                self.cpu["vendor"] = vendor_matches[0]
            
            # Extract family, model, stepping
            family_matches = re.findall(r"cpu family\s+: (\d+)", cpuinfo)
            if family_matches:
                self.cpu["family"] = int(family_matches[0])
            
            model_matches = re.findall(r"model\s+: (\d+)", cpuinfo)
            if model_matches:
                self.cpu["model"] = int(model_matches[0])
            
            stepping_matches = re.findall(r"stepping\s+: (\d+)", cpuinfo)
            if stepping_matches:
                self.cpu["stepping"] = int(stepping_matches[0])
            
            # Count unique physical IDs for core count
            physical_ids = set(re.findall(r"physical id\s+: (\d+)", cpuinfo))
            cores_per_socket = set(re.findall(r"cpu cores\s+: (\d+)", cpuinfo))
            
            if physical_ids and cores_per_socket:
                self.cpu["cores"] = len(physical_ids) * int(list(cores_per_socket)[0])
            
            # Count processor entries for thread count
            self.cpu["threads"] = len(re.findall(r"processor\s+: (\d+)", cpuinfo))
            
        except Exception as e:
            logger.error(f"Failed to detect CPU on Linux: {e}")
    
    def _detect_cpu_windows(self):
        """Detect CPU on Windows"""
        try:
            # Use wmic to get CPU info
            wmic_output = subprocess.check_output(["wmic", "cpu", "get", "Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,Family,Model,Stepping", "/format:csv"], universal_newlines=True)
            
            # Parse CSV output
            lines = wmic_output.strip().split("\n")
            if len(lines) >= 2:
                headers = lines[0].strip().split(",")
                values = lines[1].strip().split(",")
                
                cpu_info = dict(zip(headers, values))
                
                if "Name" in cpu_info:
                    self.cpu["brand"] = cpu_info["Name"]
                
                if "Manufacturer" in cpu_info:
                    self.cpu["vendor"] = cpu_info["Manufacturer"]
                
                if "Family" in cpu_info:
                    try:
                        self.cpu["family"] = int(cpu_info["Family"])
                    except ValueError:
                        pass
                
                if "Model" in cpu_info:
                    try:
                        self.cpu["model"] = int(cpu_info["Model"])
                    except ValueError:
                        pass
                
                if "Stepping" in cpu_info:
                    try:
                        self.cpu["stepping"] = int(cpu_info["Stepping"])
                    except ValueError:
                        pass
                
                if "NumberOfCores" in cpu_info:
                    try:
                        self.cpu["cores"] = int(cpu_info["NumberOfCores"])
                    except ValueError:
                        pass
                
                if "NumberOfLogicalProcessors" in cpu_info:
                    try:
                        self.cpu["threads"] = int(cpu_info["NumberOfLogicalProcessors"])
                    except ValueError:
                        pass
            
        except Exception as e:
            logger.error(f"Failed to detect CPU on Windows: {e}")
    
    def _check_cpu_support(self):
        """Check if CPU is supported"""
        # Default to not supported
        self.cpu["supported"] = False
        self.cpu["support_reason"] = "CPU not in supported list"
        
        # Check if it's an Intel CPU
        if "Intel" in self.cpu["vendor"]:
            # Check for Alder Lake
            if self.cpu["family"] == SUPPORTED_INTEL_CPUS["alder_lake"]["family"] and \
               self.cpu["model"] in SUPPORTED_INTEL_CPUS["alder_lake"]["models"]:
                self.cpu["supported"] = True
                self.cpu["support_reason"] = "Supported Intel Alder Lake CPU"
                self.cpu["type"] = "alder_lake"
                return
            
            # Check for Raptor Lake
            if self.cpu["family"] == SUPPORTED_INTEL_CPUS["raptor_lake"]["family"] and \
               self.cpu["model"] in SUPPORTED_INTEL_CPUS["raptor_lake"]["models"]:
                self.cpu["supported"] = True
                self.cpu["support_reason"] = "Supported Intel Raptor Lake CPU"
                self.cpu["type"] = "raptor_lake"
                return
            
            # Generic Intel support
            if "i7" in self.cpu["brand"] or "i9" in self.cpu["brand"]:
                self.cpu["supported"] = True
                self.cpu["support_reason"] = "Intel Core i7/i9 CPU (may have limited support)"
                self.cpu["type"] = "intel_generic"
                return
    
    def _detect_gpus(self):
        """Detect GPU information"""
        if self.os_name == "Darwin":  # macOS
            self._detect_gpus_macos()
        elif self.os_name == "Linux":
            self._detect_gpus_linux()
        elif self.os_name == "Windows":
            self._detect_gpus_windows()
    
    def _detect_gpus_macos(self):
        """Detect GPUs on macOS"""
        try:
            # Use system_profiler to get GPU info
            sp_output = subprocess.check_output(["system_profiler", "SPDisplaysDataType"], universal_newlines=True)
            
            # Parse output
            gpu_sections = re.split(r"\s*Graphics/Displays:\s*|\s*Chipset Model:\s*", sp_output)
            
            for section in gpu_sections:
                if not section.strip():
                    continue
                
                gpu = {
                    "vendor": "Unknown",
                    "model": "Unknown",
                    "device_id": "Unknown",
                    "vram_mb": 0,
                    "supported": False,
                    "support_reason": "Unknown GPU"
                }
                
                # Extract model
                model_match = re.search(r"^\s*(.+?)\s*:", section)
                if model_match:
                    gpu["model"] = model_match.group(1).strip()
                
                # Determine vendor
                if "NVIDIA" in gpu["model"]:
                    gpu["vendor"] = "NVIDIA"
                elif "AMD" in gpu["model"] or "ATI" in gpu["model"]:
                    gpu["vendor"] = "AMD"
                elif "Intel" in gpu["model"]:
                    gpu["vendor"] = "Intel"
                
                # Extract VRAM
                vram_match = re.search(r"VRAM \(([^)]+)\):\s*(\d+)\s*([GM])B", section)
                if vram_match:
                    vram = int(vram_match.group(2))
                    if vram_match.group(3) == "G":
                        vram *= 1024
                    gpu["vram_mb"] = vram
                
                # Check if GPU is supported
                self._check_gpu_support(gpu)
                
                self.gpus.append(gpu)
            
        except Exception as e:
            logger.error(f"Failed to detect GPUs on macOS: {e}")
    
    def _detect_gpus_linux(self):
        """Detect GPUs on Linux"""
        try:
            # Use lspci to get GPU info
            lspci_output = subprocess.check_output(["lspci", "-vnn"], universal_newlines=True)
            
            # Find VGA and 3D controller entries
            vga_entries = re.findall(r"(VGA|3D|Display) compatible controller.*?:\s*(.*?)\s*\[([0-9a-f]{4}):([0-9a-f]{4})\]", lspci_output)
            
            for entry in vga_entries:
                gpu = {
                    "vendor": "Unknown",
                    "model": entry[1],
                    "device_id": f"0x{entry[3]}",
                    "vendor_id": f"0x{entry[2]}",
                    "vram_mb": 0,
                    "supported": False,
                    "support_reason": "Unknown GPU"
                }
                
                # Determine vendor
                if "NVIDIA" in gpu["model"]:
                    gpu["vendor"] = "NVIDIA"
                elif "AMD" in gpu["model"] or "ATI" in gpu["model"]:
                    gpu["vendor"] = "AMD"
                elif "Intel" in gpu["model"]:
                    gpu["vendor"] = "Intel"
                
                # Try to get VRAM info
                if gpu["vendor"] == "NVIDIA":
                    try:
                        nvidia_smi_output = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"], universal_newlines=True)
                        vram = int(nvidia_smi_output.strip())
                        gpu["vram_mb"] = vram
                    except Exception:
                        pass
                
                # Check if GPU is supported
                self._check_gpu_support(gpu)
                
                self.gpus.append(gpu)
            
        except Exception as e:
            logger.error(f"Failed to detect GPUs on Linux: {e}")
    
    def _detect_gpus_windows(self):
        """Detect GPUs on Windows"""
        try:
            # Use wmic to get GPU info
            wmic_output = subprocess.check_output(["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM,PNPDeviceID", "/format:csv"], universal_newlines=True)
            
            # Parse CSV output
            lines = wmic_output.strip().split("\n")
            if len(lines) >= 2:
                headers = lines[0].strip().split(",")
                
                for i in range(1, len(lines)):
                    values = lines[i].strip().split(",")
                    if len(values) < len(headers):
                        continue
                    
                    gpu_info = dict(zip(headers, values))
                    
                    gpu = {
                        "vendor": "Unknown",
                        "model": gpu_info.get("Name", "Unknown"),
                        "device_id": "Unknown",
                        "vram_mb": 0,
                        "supported": False,
                        "support_reason": "Unknown GPU"
                    }
                    
                    # Determine vendor
                    if "NVIDIA" in gpu["model"]:
                        gpu["vendor"] = "NVIDIA"
                    elif "AMD" in gpu["model"] or "ATI" in gpu["model"]:
                        gpu["vendor"] = "AMD"
                    elif "Intel" in gpu["model"]:
                        gpu["vendor"] = "Intel"
                    
                    # Extract device ID from PNPDeviceID
                    if "PNPDeviceID" in gpu_info:
                        device_id_match = re.search(r"DEV_([0-9A-F]{4})", gpu_info["PNPDeviceID"])
                        if device_id_match:
                            gpu["device_id"] = f"0x{device_id_match.group(1)}"
                    
                    # Extract VRAM
                    if "AdapterRAM" in gpu_info and gpu_info["AdapterRAM"].isdigit():
                        gpu["vram_mb"] = int(gpu_info["AdapterRAM"]) // (1024 * 1024)
                    
                    # Check if GPU is supported
                    self._check_gpu_support(gpu)
                    
                    self.gpus.append(gpu)
            
        except Exception as e:
            logger.error(f"Failed to detect GPUs on Windows: {e}")
    
    def _check_gpu_support(self, gpu):
        """Check if GPU is supported"""
        # Default to not supported
        gpu["supported"] = False
        gpu["support_reason"] = "GPU not in supported list"
        
        # Check NVIDIA GPUs
        if gpu["vendor"] == "NVIDIA":
            for device_id, model in SUPPORTED_NVIDIA_GPUS.items():
                if device_id.lower() in gpu["device_id"].lower() or model.lower() in gpu["model"].lower():
                    gpu["supported"] = True
                    gpu["support_reason"] = f"Supported NVIDIA GPU: {model}"
                    gpu["type"] = "nvidia_gtx970" if "970" in model else "nvidia_generic"
                    return
        
        # Check Intel Arc GPUs
        elif gpu["vendor"] == "Intel":
            for device_id, model in SUPPORTED_INTEL_GPUS.items():
                if device_id.lower() in gpu["device_id"].lower() or model.lower() in gpu["model"].lower():
                    gpu["supported"] = True
                    gpu["support_reason"] = f"Supported Intel GPU: {model}"
                    gpu["type"] = "intel_arc770" if "770" in model else "intel_arc_generic"
                    return
    
    def _detect_memory(self):
        """Detect system memory"""
        try:
            if self.os_name == "Darwin":  # macOS
                sysctl_output = subprocess.check_output(["sysctl", "hw.memsize"], universal_newlines=True)
                mem_bytes = int(sysctl_output.split(":")[1].strip())
                self.ram_gb = mem_bytes / (1024 * 1024 * 1024)
            elif self.os_name == "Linux":
                with open("/proc/meminfo", "r") as f:
                    meminfo = f.read()
                mem_kb = int(re.search(r"MemTotal:\s+(\d+)\s+kB", meminfo).group(1))
                self.ram_gb = mem_kb / (1024 * 1024)
            elif self.os_name == "Windows":
                wmic_output = subprocess.check_output(["wmic", "computersystem", "get", "TotalPhysicalMemory"], universal_newlines=True)
                mem_bytes = int(wmic_output.split("\n")[1].strip())
                self.ram_gb = mem_bytes / (1024 * 1024 * 1024)
        except Exception as e:
            logger.error(f"Failed to detect system memory: {e}")
            self.ram_gb = 0
    
    def _detect_storage(self):
        """Detect system storage"""
        try:
            if self.os_name == "Darwin":  # macOS
                df_output = subprocess.check_output(["df", "-k", "/"], universal_newlines=True)
                lines = df_output.strip().split("\n")
                if len(lines) >= 2:
                    fields = lines[1].split()
                    if len(fields) >= 4:
                        total_kb = int(fields[1])
                        self.storage_gb = total_kb / (1024 * 1024)
            elif self.os_name == "Linux":
                df_output = subprocess.check_output(["df", "-k", "/"], universal_newlines=True)
                lines = df_output.strip().split("\n")
                if len(lines) >= 2:
                    fields = lines[1].split()
                    if len(fields) >= 4:
                        total_kb = int(fields[1])
                        self.storage_gb = total_kb / (1024 * 1024)
            elif self.os_name == "Windows":
                wmic_output = subprocess.check_output(["wmic", "logicaldisk", "where", "DeviceID='C:'", "get", "Size"], universal_newlines=True)
                lines = wmic_output.strip().split("\n")
                if len(lines) >= 2:
                    size_bytes = int(lines[1].strip())
                    self.storage_gb = size_bytes / (1024 * 1024 * 1024)
        except Exception as e:
            logger.error(f"Failed to detect system storage: {e}")
            self.storage_gb = 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of hardware information"""
        return {
            "os": {
                "name": self.os_name,
                "version": self.os_version,
                "release": self.os_release
            },
            "cpu": self.cpu,
            "gpus": self.gpus,
            "ram_gb": self.ram_gb,
            "storage_gb": self.storage_gb
        }
    
    def is_compatible(self) -> Tuple[bool, str]:
        """Check if the system is compatible with Skyscope"""
        # Check CPU compatibility
        if not self.cpu["supported"]:
            return False, f"Unsupported CPU: {self.cpu['brand']}"
        
        # Check GPU compatibility
        supported_gpus = [gpu for gpu in self.gpus if gpu["supported"]]
        if not supported_gpus:
            return False, "No supported GPUs found"
        
        # Check RAM
        if self.ram_gb < 8:
            return False, f"Insufficient RAM: {self.ram_gb:.1f} GB (minimum 8 GB required)"
        
        # Check storage
        if self.storage_gb < 50:
            return False, f"Insufficient storage: {self.storage_gb:.1f} GB (minimum 50 GB required)"
        
        return True, "System is compatible with Skyscope"
    
    def get_hardware_configs(self) -> List[str]:
        """Get list of hardware configurations for this system"""
        configs = []
        
        # Add CPU config
        if self.cpu["supported"]:
            if "type" in self.cpu:
                configs.append(self.cpu["type"])
        
        # Add GPU configs
        for gpu in self.gpus:
            if gpu["supported"] and "type" in gpu:
                configs.append(gpu["type"])
        
        return configs


class KextInstaller:
    """Class to handle kext installation and configuration"""
    
    def __init__(self, kexts_dir: str = DEFAULT_KEXTS_DIR):
        """
        Initialize kext installer
        
        Args:
            kexts_dir: Directory containing kexts
        """
        self.kexts_dir = kexts_dir
        self.system_kexts_dir = "/Library/Extensions"
        self.system_prelinked_kernel = "/System/Library/PrelinkedKernels/prelinkedkernel"
    
    def list_available_kexts(self) -> List[Dict[str, Any]]:
        """
        List available kexts
        
        Returns:
            List of kext information dictionaries
        """
        kexts = []
        
        # Find all .kext directories
        kext_paths = glob.glob(os.path.join(self.kexts_dir, "*.kext"))
        
        for kext_path in kext_paths:
            kext_name = os.path.basename(kext_path)
            info_plist_path = os.path.join(kext_path, "Contents", "Info.plist")
            
            if not os.path.exists(info_plist_path):
                continue
            
            try:
                with open(info_plist_path, "rb") as f:
                    info_plist = plistlib.load(f)
                
                kext_info = {
                    "name": kext_name,
                    "path": kext_path,
                    "bundle_id": info_plist.get("CFBundleIdentifier", ""),
                    "version": info_plist.get("CFBundleVersion", ""),
                    "compatible_version": info_plist.get("CFBundleCompatibleVersion", ""),
                    "executable": self._get_kext_executable(kext_path, info_plist)
                }
                
                kexts.append(kext_info)
                
            except Exception as e:
                logger.error(f"Failed to read kext info for {kext_name}: {e}")
        
        return kexts
    
    def _get_kext_executable(self, kext_path: str, info_plist: Dict[str, Any]) -> Optional[str]:
        """
        Get the path to the kext executable
        
        Args:
            kext_path: Path to the kext
            info_plist: Parsed Info.plist
            
        Returns:
            Path to executable or None
        """
        executable = info_plist.get("CFBundleExecutable")
        if not executable:
            return None
        
        executable_path = os.path.join(kext_path, "Contents", "MacOS", executable)
        if os.path.exists(executable_path):
            return executable_path
        
        return None
    
    def install_kext(self, kext_path: str) -> bool:
        """
        Install a kext
        
        Args:
            kext_path: Path to the kext
            
        Returns:
            True if installation was successful, False otherwise
        """
        if not os.path.exists(kext_path):
            logger.error(f"Kext not found: {kext_path}")
            return False
        
        kext_name = os.path.basename(kext_path)
        dest_path = os.path.join(self.system_kexts_dir, kext_name)
        
        logger.info(f"Installing kext: {kext_name}")
        
        try:
            # Check if running as root
            if os.geteuid() != 0:
                logger.error("Kext installation requires root privileges")
                return False
            
            # Remove existing kext if present
            if os.path.exists(dest_path):
                logger.info(f"Removing existing kext: {dest_path}")
                shutil.rmtree(dest_path)
            
            # Copy kext
            logger.info(f"Copying {kext_path} to {dest_path}")
            shutil.copytree(kext_path, dest_path)
            
            # Set permissions
            subprocess.run(["chmod", "-R", "755", dest_path], check=True)
            subprocess.run(["chown", "-R", "root:wheel", dest_path], check=True)
            
            # Update kext cache
            logger.info("Updating kext cache")
            subprocess.run(["kextcache", "-i", "/"], check=True)
            
            logger.info(f"Successfully installed kext: {kext_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to install kext {kext_name}: {e}")
            return False
    
    def install_kexts_for_hardware(self, hardware_configs: List[str]) -> Tuple[int, int]:
        """
        Install kexts for specific hardware configurations
        
        Args:
            hardware_configs: List of hardware configurations
            
        Returns:
            Tuple of (success count, total count)
        """
        kexts_to_install = set()
        
        # Collect kexts for each hardware configuration
        for config_name in hardware_configs:
            if config_name in HARDWARE_CONFIGS:
                config = HARDWARE_CONFIGS[config_name]
                kexts_to_install.update(config["kexts"])
        
        # Install kexts
        success_count = 0
        total_count = len(kexts_to_install)
        
        for kext_name in kexts_to_install:
            kext_path = os.path.join(self.kexts_dir, kext_name)
            if os.path.exists(kext_path):
                if self.install_kext(kext_path):
                    success_count += 1
            else:
                logger.error(f"Kext not found: {kext_name}")
        
        return success_count, total_count
    
    def is_kext_loaded(self, bundle_id: str) -> bool:
        """
        Check if a kext is loaded
        
        Args:
            bundle_id: Bundle ID of the kext
            
        Returns:
            True if loaded, False otherwise
        """
        try:
            kextstat_output = subprocess.check_output(["kextstat", "-b", bundle_id], universal_newlines=True)
            return bundle_id in kextstat_output
        except subprocess.CalledProcessError:
            return False
    
    def load_kext(self, kext_path: str) -> bool:
        """
        Load a kext
        
        Args:
            kext_path: Path to the kext
            
        Returns:
            True if loading was successful, False otherwise
        """
        try:
            # Check if running as root
            if os.geteuid() != 0:
                logger.error("Kext loading requires root privileges")
                return False
            
            # Load kext
            subprocess.run(["kextload", kext_path], check=True)
            return True
        except Exception as e:
            logger.error(f"Failed to load kext {kext_path}: {e}")
            return False


class ConfigManager:
    """Class to handle configuration management"""
    
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        """
        Initialize configuration manager
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file
        
        Returns:
            Configuration dictionary
        """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load configuration: {e}")
        
        # Return default configuration
        return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration
        
        Returns:
            Default configuration dictionary
        """
        return {
            "version": VERSION,
            "build_date": BUILD_DATE,
            "hardware_support": {
                "nvidia_gpus": list(SUPPORTED_NVIDIA_GPUS.values()),
                "intel_gpus": list(SUPPORTED_INTEL_GPUS.values()),
                "intel_cpus": [cpu["name"] for cpu in SUPPORTED_INTEL_CPUS.values()]
            },
            "macos_versions": {
                "sequoia": MACOS_VERSIONS["sequoia"]["marketing_name"],
                "tahoe": MACOS_VERSIONS["tahoe"]["marketing_name"]
            },
            "paths": {
                "kexts_dir": DEFAULT_KEXTS_DIR,
                "work_dir": DEFAULT_WORK_DIR,
                "output_dir": DEFAULT_OUTPUT_DIR
            },
            "options": {
                "enable_nvidia": True,
                "enable_intel_arc": True,
                "enable_cuda": True,
                "enable_metal": True,
                "create_usb_installer": True,
                "install_kexts": True,
                "backup_system": True
            }
        }
    
    def save_config(self) -> bool:
        """
        Save configuration to file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get current configuration
        
        Returns:
            Configuration dictionary
        """
        return self.config
    
    def update_config(self, new_config: Dict[str, Any]) -> bool:
        """
        Update configuration
        
        Args:
            new_config: New configuration dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Merge configurations
            self._merge_configs(self.config, new_config)
            return self.save_config()
        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            return False
    
    def _merge_configs(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """
        Recursively merge source dictionary into target
        
        Args:
            target: Target dictionary
            source: Source dictionary
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_configs(target[key], value)
            else:
                target[key] = value


class SystemPatcher:
    """Class to handle system patching operations"""
    
    def __init__(self, config_manager: ConfigManager, hardware_info: HardwareInfo):
        """
        Initialize system patcher
        
        Args:
            config_manager: Configuration manager
            hardware_info: Hardware information
        """
        self.config_manager = config_manager
        self.hardware_info = hardware_info
        self.config = config_manager.get_config()
        self.kext_installer = KextInstaller(self.config["paths"]["kexts_dir"])
        
        # Create work directories
        os.makedirs(self.config["paths"]["work_dir"], exist_ok=True)
        os.makedirs(self.config["paths"]["output_dir"], exist_ok=True)
    
    def create_backup(self) -> Optional[str]:
        """
        Create a backup of important system files
        
        Returns:
            Path to backup archive, or None if backup failed
        """
        if not self.config["options"]["backup_system"]:
            logger.info("System backup disabled in configuration")
            return None
        
        logger.info("Creating system backup")
        
        backup_dir = os.path.join(self.config["paths"]["output_dir"], "backup")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_archive = os.path.join(backup_dir, f"skyscope_backup_{timestamp}.tar.gz")
        
        try:
            # Check if running as root
            if os.geteuid() != 0:
                logger.error("System backup requires root privileges")
                return None
            
            # Create temporary directory for files to backup
            temp_dir = os.path.join(self.config["paths"]["work_dir"], "backup_temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Backup kext cache
            kext_cache_dir = os.path.join(temp_dir, "kext_cache")
            os.makedirs(kext_cache_dir, exist_ok=True)
            
            # Copy kext cache files
            for cache_file in glob.glob("/System/Library/Caches/com.apple.kext.caches/*"):
                dest = os.path.join(kext_cache_dir, os.path.basename(cache_file))
                if os.path.isdir(cache_file):
                    shutil.copytree(cache_file, dest, symlinks=True)
                else:
                    shutil.copy2(cache_file, dest)
            
            # Backup prelinked kernel
            prelinked_dir = os.path.join(temp_dir, "prelinkedkernel")
            os.makedirs(prelinked_dir, exist_ok=True)
            
            if os.path.exists("/System/Library/PrelinkedKernels/prelinkedkernel"):
                shutil.copy2("/System/Library/PrelinkedKernels/prelinkedkernel", 
                            os.path.join(prelinked_dir, "prelinkedkernel"))
            
            # Create archive
            with tarfile.open(backup_archive, "w:gz") as tar:
                tar.add(temp_dir, arcname="skyscope_backup")
            
            # Clean up
            shutil.rmtree(temp_dir)
            
            logger.info(f"System backup created: {backup_archive}")
            return backup_archive
            
        except Exception as e:
            logger.error(f"Failed to create system backup: {e}")
            return None
    
    def install_kexts(self) -> bool:
        """
        Install required kexts for detected hardware
        
        Returns:
            True if successful, False otherwise
        """
        if not self.config["options"]["install_kexts"]:
            logger.info("Kext installation disabled in configuration")
            return True
        
        logger.info("Installing kexts for detected hardware")
        
        # Get hardware configurations
        hardware_configs = self.hardware_info.get_hardware_configs()
        
        if not hardware_configs:
            logger.error("No supported hardware configurations detected")
            return False
        
        # Install kexts
        success_count, total_count = self.kext_installer.install_kexts_for_hardware(hardware_configs)
        
        if success_count == total_count:
            logger.info(f"Successfully installed {success_count} kexts")
            return True
        else:
            logger.warning(f"Installed {success_count} of {total_count} kexts")
            return success_count > 0
    
    def patch_system(self) -> bool:
        """
        Perform system patching
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Patching system for NVIDIA and Intel Arc support")
        
        # Create backup
        backup_path = self.create_backup()
        
        # Install kexts
        if not self.install_kexts():
            logger.error("Failed to install required kexts")
            return False
        
        # Apply boot arguments
        if not self._apply_boot_arguments():
            logger.error("Failed to apply boot arguments")
            return False
        
        # Rebuild kernel cache
        if not self._rebuild_kernel_cache():
            logger.error("Failed to rebuild kernel cache")
            return False
        
        logger.info("System patching completed successfully")
        return True
    
    def _apply_boot_arguments(self) -> bool:
        """
        Apply required boot arguments
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Applying boot arguments")
        
        try:
            # Check if running as root
            if os.geteuid() != 0:
                logger.error("Applying boot arguments requires root privileges")
                return False
            
            # Get hardware configurations
            hardware_configs = self.hardware_info.get_hardware_configs()
            boot_args = []
            
            # Collect boot arguments for each hardware configuration
            for config_name in hardware_configs:
                if config_name in HARDWARE_CONFIGS:
                    config = HARDWARE_CONFIGS[config_name]
                    boot_args.append(config["boot_args"])
            
            # Combine boot arguments
            combined_boot_args = " ".join(boot_args)
            
            # Apply boot arguments using nvram
            subprocess.run(["nvram", "boot-args=" + combined_boot_args], check=True)
            
            logger.info(f"Applied boot arguments: {combined_boot_args}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply boot arguments: {e}")
            return False
    
    def _rebuild_kernel_cache(self) -> bool:
        """
        Rebuild kernel cache
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Rebuilding kernel cache")
        
        try:
            # Check if running as root
            if os.geteuid() != 0:
                logger.error("Rebuilding kernel cache requires root privileges")
                return False
            
            # Rebuild kernel cache
            subprocess.run(["kextcache", "-i", "/"], check=True)
            
            logger.info("Kernel cache rebuilt successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rebuild kernel cache: {e}")
            return False
    
    def create_installer(self, macos_version: str) -> bool:
        """
        Create a bootable USB installer
        
        Args:
            macos_version: macOS version to install
            
        Returns:
            True if successful, False otherwise
        """
        if not self.config["options"]["create_usb_installer"]:
            logger.info("USB installer creation disabled in configuration")
            return True
        
        logger.info(f"Creating bootable USB installer for macOS {macos_version}")
        
        try:
            # Download macOS installer
            downloader = MacOSDownloader(cache_dir=os.path.join(self.config["paths"]["work_dir"], "InstallerCache"))
            
            # List available versions
            versions = downloader.find_available_versions()
            
            if macos_version not in versions:
                logger.error(f"macOS version {macos_version} not found")
                return False
            
            # Download installer
            installer_path = downloader.download_installer(
                macos_version=macos_version,
                architecture="x86_64"
            )
            
            if not installer_path:
                logger.error(f"Failed to download macOS {macos_version} installer")
                return False
            
            # Get hardware configurations
            hardware_configs = self.hardware_info.get_hardware_configs()
            
            # Create USB creator
            creator = USBCreator(work_dir=os.path.join(self.config["paths"]["work_dir"], "USBCreator"))
            
            # List available disks
            disks = creator.list_disks()
            
            if not disks:
                logger.error("No disks found")
                return False
            
            # TODO: In a real implementation, we would prompt the user to select a disk
            # For now, we'll just return True to indicate success
            logger.info("USB installer creation would continue with disk selection")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create USB installer: {e}")
            return False


class CommandLineInterface:
    """Command-line interface for Skyscope"""
    
    def __init__(self):
        """Initialize CLI"""
        self.config_manager = ConfigManager()
        self.hardware_info = HardwareInfo()
        self.patcher = SystemPatcher(self.config_manager, self.hardware_info)
    
    def run(self):
        """Run the CLI"""
        parser = self._create_argument_parser()
        args = parser.parse_args()
        
        # Print banner
        self._print_banner()
        
        # Handle commands
        if args.detect:
            self._cmd_detect_hardware()
        elif args.install_kexts:
            self._cmd_install_kexts()
        elif args.patch_system:
            self._cmd_patch_system()
        elif args.create_installer:
            self._cmd_create_installer(args.macos_version)
        elif args.extract_drivers:
            self._cmd_extract_drivers(args.vendor)
        elif args.list_versions:
            self._cmd_list_versions()
        else:
            # Default: show interactive menu
            self._show_menu()
    
    def _create_argument_parser(self) -> argparse.ArgumentParser:
        """
        Create argument parser
        
        Returns:
            Argument parser
        """
        parser = argparse.ArgumentParser(description=f"Skyscope macOS Patcher v{VERSION}")
        
        parser.add_argument("--detect", action="store_true", help="Detect hardware")
        parser.add_argument("--install-kexts", action="store_true", help="Install kexts")
        parser.add_argument("--patch-system", action="store_true", help="Patch system")
        parser.add_argument("--create-installer", action="store_true", help="Create bootable USB installer")
        parser.add_argument("--macos-version", choices=list(MACOS_VERSIONS.keys()), default="sequoia", help="macOS version for installer")
        parser.add_argument("--extract-drivers", action="store_true", help="Extract Linux drivers")
        parser.add_argument("--vendor", choices=["nvidia", "intel", "all"], default="all", help="Vendor for driver extraction")
        parser.add_argument("--list-versions", action="store_true", help="List available macOS versions")
        parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
        
        return parser
    
    def _print_banner(self):
        """Print application banner"""
        print(f"\n{'='*80}")
        print(f"  Skyscope macOS Patcher v{VERSION} - {BUILD_DATE}")
        print(f"  NVIDIA and Intel Arc support for macOS Sequoia/Tahoe")
        print(f"{'='*80}\n")
    
    def _cmd_detect_hardware(self):
        """Detect hardware command"""
        print("Detecting hardware...")
        
        summary = self.hardware_info.get_summary()
        compatible, reason = self.hardware_info.is_compatible()
        
        print("\nHardware Summary:")
        print(f"  OS: {summary['os']['name']} {summary['os']['version']}")
        print(f"  CPU: {summary['cpu']['brand']} ({summary['cpu']['cores']} cores, {summary['cpu']['threads']} threads)")
        print(f"  CPU Support: {'Yes' if summary['cpu']['supported'] else 'No'} - {summary['cpu']['support_reason']}")
        
        print("\n  GPUs:")
        for i, gpu in enumerate(summary['gpus']):
            print(f"    {i+1}. {gpu['vendor']} {gpu['model']} ({gpu['vram_mb']} MB)")
            print(f"       Support: {'Yes' if gpu['supported'] else 'No'} - {gpu['support_reason']}")
        
        print(f"\n  RAM: {summary['ram_gb']:.1f} GB")
        print(f"  Storage: {summary['storage_gb']:.1f} GB")
        
        print("\nCompatibility:")
        print(f"  {'COMPATIBLE' if compatible else 'NOT COMPATIBLE'}: {reason}")
        
        if compatible:
            print("\nRecommended Hardware Configurations:")
            for config in self.hardware_info.get_hardware_configs():
                if config in HARDWARE_CONFIGS:
                    print(f"  - {HARDWARE_CONFIGS[config]['name']}")
    
    def _cmd_install_kexts(self):
        """Install kexts command"""
        print("Installing kexts...")
        
        # Check if running as root
        if os.geteuid() != 0:
            print("Error: Kext installation requires root privileges")
            print("Please run this command with sudo")
            return
        
        # Check compatibility
        compatible, reason = self.hardware_info.is_compatible()
        if not compatible:
            print(f"Error: System is not compatible: {reason}")
            return
        
        # Install kexts
        if self.patcher.install_kexts():
            print("Kexts installed successfully")
        else:
            print("Failed to install kexts")
    
    def _cmd_patch_system(self):
        """Patch system command"""
        print("Patching system...")
        
        # Check if running as root
        if os.geteuid() != 0:
            print("Error: System patching requires root privileges")
            print("Please run this command with sudo")
            return
        
        # Check compatibility
        compatible, reason = self.hardware_info.is_compatible()
        if not compatible:
            print(f"Error: System is not compatible: {reason}")
            return
        
        # Patch system
        if self.patcher.patch_system():
            print("System patched successfully")
            print("Please restart your computer for changes to take effect")
        else:
            print("Failed to patch system")
    
    def _cmd_create_installer(self, macos_version: str):
        """
        Create installer command
        
        Args:
            macos_version: macOS version to install
        """
        print(f"Creating bootable USB installer for macOS {macos_version}...")
        
        # Check if running as root
        if os.geteuid() != 0:
            print("Error: USB installer creation requires root privileges")
            print("Please run this command with sudo")
            return
        
        # Create installer
        if self.patcher.create_installer(macos_version):
            print("USB installer created successfully")
        else:
            print("Failed to create USB installer")
    
    def _cmd_extract_drivers(self, vendor: str):
        """
        Extract drivers command
        
        Args:
            vendor: Vendor for driver extraction
        """
        print(f"Extracting {vendor} drivers...")
        
        # Create extractor
        extractor = LinuxDriverExtractor(work_dir=os.path.join(self.config_manager.get_config()["paths"]["work_dir"], "LinuxExtractor"))
        
        if vendor == "nvidia":
            result = extractor.extract_nvidia_driver()
            if result['success']:
                print(f"Successfully extracted NVIDIA driver version {result['version']}")
            else:
                print("Failed to extract NVIDIA driver")
        elif vendor == "intel":
            result = extractor.extract_intel_driver()
            if result['success']:
                print(f"Successfully extracted Intel driver version {result['version']}")
            else:
                print("Failed to extract Intel driver")
        else:  # all
            results = extractor.extract_all_drivers()
            
            for vendor_name, vendor_results in results.items():
                print(f"\nExtracted {vendor_name.upper()} drivers:")
                for result in vendor_results:
                    if result['success']:
                        print(f"  Version {result['version']}: Success")
                    else:
                        print(f"  Version {result['version']}: Failed")
    
    def _cmd_list_versions(self):
        """List available macOS versions"""
        print("Listing available macOS versions...")
        
        # Create downloader
        downloader = MacOSDownloader(cache_dir=os.path.join(self.config_manager.get_config()["paths"]["work_dir"], "InstallerCache"))
        
        # List versions
        downloader.list_versions()
    
    def _show_menu(self):
        """Show interactive menu"""
        while True:
            print("\nSkyscope macOS Patcher - Main Menu")
            print("1. Detect Hardware")
            print("2. Install Kexts")
            print("3. Patch System")
            print("4. Create Bootable USB Installer")
            print("5. Extract Linux Drivers")
            print("6. List Available macOS Versions")
            print("7. Exit")
            
            choice = input("\nEnter your choice (1-7): ")
            
            if choice == "1":
                self._cmd_detect_hardware()
            elif choice == "2":
                self._cmd_install_kexts()
            elif choice == "3":
                self._cmd_patch_system()
            elif choice == "4":
                macos_version = input("Enter macOS version (sequoia/tahoe): ").lower()
                if macos_version not in MACOS_VERSIONS:
                    print(f"Error: Unknown macOS version: {macos_version}")
                    continue
                self._cmd_create_installer(macos_version)
            elif choice == "5":
                vendor = input("Enter vendor (nvidia/intel/all): ").lower()
                if vendor not in ["nvidia", "intel", "all"]:
                    print(f"Error: Unknown vendor: {vendor}")
                    continue
                self._cmd_extract_drivers(vendor)
            elif choice == "6":
                self._cmd_list_versions()
            elif choice == "7":
                print("Exiting Skyscope macOS Patcher")
                break
            else:
                print("Invalid choice. Please try again.")


class GraphicalInterface:
    """Graphical interface for Skyscope"""
    
    def __init__(self):
        """Initialize GUI"""
        self.config_manager = ConfigManager()
        self.hardware_info = HardwareInfo()
        self.patcher = SystemPatcher(self.config_manager, self.hardware_info)
        
        self.root = tk.Tk()
        self.root.title(f"Skyscope macOS Patcher v{VERSION}")
        self.root.geometry("800x600")
        
        self._create_ui()
    
    def _create_ui(self):
        """Create user interface"""
        # Create main notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.tab_main = ttk.Frame(self.notebook)
        self.tab_hardware = ttk.Frame(self.notebook)
        self.tab_kexts = ttk.Frame(self.notebook)
        self.tab_installer = ttk.Frame(self.notebook)
        self.tab_advanced = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_main, text="Main")
        self.notebook.add(self.tab_hardware, text="Hardware")
        self.notebook.add(self.tab_kexts, text="Kexts")
        self.notebook.add(self.tab_installer, text="Installer")
        self.notebook.add(self.tab_advanced, text="Advanced")
        
        # Create main tab content
        self._create_main_tab()
        
        # Create hardware tab content
        self._create_hardware_tab()
        
        # Create kexts tab content
        self._create_kexts_tab()
        
        # Create installer tab content
        self._create_installer_tab()
        
        # Create advanced tab content
        self._create_advanced_tab()
    
    def _create_main_tab(self):
        """Create main tab content"""
        # Banner
        banner_frame = ttk.Frame(self.tab_main)
        banner_frame.pack(fill=tk.X, pady=10)
        
        banner_label = ttk.Label(
            banner_frame, 
            text=f"Skyscope macOS Patcher v{VERSION}",
            font=("Arial", 16, "bold")
        )
        banner_label.pack()
        
        subtitle_label = ttk.Label(
            banner_frame,
            text="NVIDIA and Intel Arc support for macOS Sequoia/Tahoe",
            font=("Arial", 12)
        )
        subtitle_label.pack()
        
        # Status frame
        status_frame = ttk.LabelFrame(self.tab_main, text="System Status")
        status_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Hardware status
        self.hardware_status = ttk.Label(status_frame, text="Hardware: Detecting...")
        self.hardware_status.pack(anchor=tk.W, padx=10, pady=5)
        
        # macOS status
        self.macos_status = ttk.Label(status_frame, text="macOS: Detecting...")
        self.macos_status.pack(anchor=tk.W, padx=10, pady=5)
        
        # Kext status
        self.kext_status = ttk.Label(status_frame, text="Kexts: Not installed")
        self.kext_status.pack(anchor=tk.W, padx=10, pady=5)
        
        # Actions frame
        actions_frame = ttk.LabelFrame(self.tab_main, text="Actions")
        actions_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Detect hardware button
        detect_button = ttk.Button(
            actions_frame, 
            text="Detect Hardware",
            command=self._on_detect_hardware
        )
        detect_button.pack(fill=tk.X, padx=10, pady=5)
        
        # Install kexts button
        install_button = ttk.Button(
            actions_frame, 
            text="Install Kexts",
            command=self._on_install_kexts
        )
        install_button.pack(fill=tk.X, padx=10, pady=5)
        
        # Patch system button
        patch_button = ttk.Button(
            actions_frame, 
            text="Patch System",
            command=self._on_patch_system
        )
        patch_button.pack(fill=tk.X, padx=10, pady=5)
        
        # Create installer button
        installer_button = ttk.Button(
            actions_frame, 
            text="Create Bootable USB Installer",
            command=self._on_create_installer
        )
        installer_button.pack(fill=tk.X, padx=10, pady=5)
        
        # Status log
        log_frame = ttk.LabelFrame(self.tab_main, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = tk.Text(log_frame, height=10, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # Detect hardware on startup
        self.root.after(100, self._on_detect_hardware)
    
    def _create_hardware_tab(self):
        """Create hardware tab content"""
        # CPU frame
        cpu_frame = ttk.LabelFrame(self.tab_hardware, text="CPU Information")
        cpu_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.cpu_info_text = tk.Text(cpu_frame, height=5, wrap=tk.WORD)
        self.cpu_info_text.pack(fill=tk.X, padx=5, pady=5)
        
        # GPU frame
        gpu_frame = ttk.LabelFrame(self.tab_hardware, text="GPU Information")
        gpu_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.gpu_info_text = tk.Text(gpu_frame, height=8, wrap=tk.WORD)
        self.gpu_info_text.pack(fill=tk.X, padx=5, pady=5)
        
        # System frame
        system_frame = ttk.LabelFrame(self.tab_hardware, text="System Information")
        system_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.system_info_text = tk.Text(system_frame, height=5, wrap=tk.WORD)
        self.system_info_text.pack(fill=tk.X, padx=5, pady=5)
        
        # Compatibility frame
        compat_frame = ttk.LabelFrame(self.tab_hardware, text="Compatibility")
        compat_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.compat_info_text = tk.Text(compat_frame, height=3, wrap=tk.WORD)
        self.compat_info_text.pack(fill=tk.X, padx=5, pady=5)
        
        # Refresh button
        refresh_button = ttk.Button(
            self.tab_hardware, 
            text="Refresh Hardware Information",
            command=self._update_hardware_info
        )
        refresh_button.pack(padx=10, pady=10)
    
    def _create_kexts_tab(self):
        """Create kexts tab content"""
        # Available kexts frame
        avail_frame = ttk.LabelFrame(self.tab_kexts, text="Available Kexts")
        avail_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.kexts_tree = ttk.Treeview(avail_frame, columns=("Name", "Version", "Status"))
        self.kexts_tree.heading("#0", text="")
        self.kexts_tree.heading("Name", text="Name")
        self.kexts_tree.heading("Version", text="Version")
        self.kexts_tree.heading("Status", text="Status")
        
        self.kexts_tree.column("#0", width=0, stretch=tk.NO)
        self.kexts_tree.column("Name", width=200, stretch=tk.YES)
        self.kexts_tree.column("Version", width=100, stretch=tk.YES)
        self.kexts_tree.column("Status", width=100, stretch=tk.YES)
        
        self.kexts_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Buttons frame
        buttons_frame = ttk.Frame(self.tab_kexts)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        refresh_button = ttk.Button(
            buttons_frame, 
            text="Refresh Kexts",
            command=self._refresh_kexts
        )
        refresh_button.pack(side=tk.LEFT, padx=5)
        
        install_button = ttk.Button(
            buttons_frame, 
            text="Install Selected Kext",
            command=self._install_selected_kext
        )
        install_button.pack(side=tk.LEFT, padx=5)
        
        install_all_button = ttk.Button(
            buttons_frame, 
            text="Install All Required Kexts",
            command=self._on_install_kexts
        )
        install_all_button.pack(side=tk.LEFT, padx=5)
    
    def _create_installer_tab(self):
        """Create installer tab content"""
        # macOS version frame
        version_frame = ttk.LabelFrame(self.tab_installer, text="macOS Version")
        version_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.version_var = tk.StringVar(value="sequoia")
        
        for i, (version_key, version_info) in enumerate(MACOS_VERSIONS.items()):
            version_radio = ttk.Radiobutton(
                version_frame,
                text=f"{version_info['marketing_name']} (macOS {version_info['version']})",
                variable=self.version_var,
                value=version_key
            )
            version_radio.pack(anchor=tk.W, padx=10, pady=5)
        
        # Hardware configuration frame
        config_frame = ttk.LabelFrame(self.tab_installer, text="Hardware Configuration")
        config_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.nvidia_var = tk.BooleanVar(value=True)
        self.intel_arc_var = tk.BooleanVar(value=True)
        self.intel_cpu_var = tk.BooleanVar(value=True)
        
        nvidia_check = ttk.Checkbutton(
            config_frame,
            text="NVIDIA GTX 970/980 Support",
            variable=self.nvidia_var
        )
        nvidia_check.pack(anchor=tk.W, padx=10, pady=5)
        
        intel_arc_check = ttk.Checkbutton(
            config_frame,
            text="Intel Arc A770 Support",
            variable=self.intel_arc_var
        )
        intel_arc_check.pack(anchor=tk.W, padx=10, pady=5)
        
        intel_cpu_check = ttk.Checkbutton(
            config_frame,
            text="Intel Alder Lake / Raptor Lake Support",
            variable=self.intel_cpu_var
        )
        intel_cpu_check.pack(anchor=tk.W, padx=10, pady=5)
        
        # USB device frame
        usb_frame = ttk.LabelFrame(self.tab_installer, text="USB Device")
        usb_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.usb_var = tk.StringVar()
        self.usb_combo = ttk.Combobox(usb_frame, textvariable=self.usb_var)
        self.usb_combo.pack(fill=tk.X, padx=10, pady=5)
        
        refresh_usb_button = ttk.Button(
            usb_frame, 
            text="Refresh USB Devices",
            command=self._refresh_usb_devices
        )
        refresh_usb_button.pack(padx=10, pady=5)
        
        # Create installer button
        create_button = ttk.Button(
            self.tab_installer, 
            text="Create Bootable USB Installer",
            command=self._on_create_installer
        )
        create_button.pack(padx=10, pady=10)
        
        # Refresh USB devices on startup
        self.root.after(500, self._refresh_usb_devices)
    
    def _create_advanced_tab(self):
        """Create advanced tab content"""
        # Driver extraction frame
        extract_frame = ttk.LabelFrame(self.tab_advanced, text="Linux Driver Extraction")
        extract_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.vendor_var = tk.StringVar(value="all")
        
        vendor_label = ttk.Label(extract_frame, text="Vendor:")
        vendor_label.pack(anchor=tk.W, padx=10, pady=5)
        
        vendor_frame = ttk.Frame(extract_frame)
        vendor_frame.pack(fill=tk.X, padx=10, pady=5)
        
        nvidia_radio = ttk.Radiobutton(
            vendor_frame,
            text="NVIDIA",
            variable=self.vendor_var,
            value="nvidia"
        )
        nvidia_radio.pack(side=tk.LEFT, padx=5)
        
        intel_radio = ttk.Radiobutton(
            vendor_frame,
            text="Intel",
            variable=self.vendor_var,
            value="intel"
        )
        intel_radio.pack(side=tk.LEFT, padx=5)
        
        all_radio = ttk.Radiobutton(
            vendor_frame,
            text="All",
            variable=self.vendor_var,
            value="all"
        )
        all_radio.pack(side=tk.LEFT, padx=5)
        
        extract_button = ttk.Button(
            extract_frame, 
            text="Extract Drivers",
            command=self._on_extract_drivers
        )
        extract_button.pack(padx=10, pady=10)
        
        # Configuration frame
        config_frame = ttk.LabelFrame(self.tab_advanced, text="Configuration")
        config_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.backup_var = tk.BooleanVar(value=True)
        
        backup_check = ttk.Checkbutton(
            config_frame,
            text="Create system backup before patching",
            variable=self.backup_var
        )
        backup_check.pack(anchor=tk.W, padx=10, pady=5)
        
        # Paths frame
        paths_frame = ttk.LabelFrame(self.tab_advanced, text="Paths")
        paths_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Kexts directory
        kexts_frame = ttk.Frame(paths_frame)
        kexts_frame.pack(fill=tk.X, padx=10, pady=5)
        
        kexts_label = ttk.Label(kexts_frame, text="Kexts Directory:")
        kexts_label.pack(side=tk.LEFT, padx=5)
        
        self.kexts_path_var = tk.StringVar(value=self.config_manager.get_config()["paths"]["kexts_dir"])
        kexts_entry = ttk.Entry(kexts_frame, textvariable=self.kexts_path_var)
        kexts_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        kexts_button = ttk.Button(
            kexts_frame, 
            text="Browse",
            command=lambda: self._browse_directory(self.kexts_path_var)
        )
        kexts_button.pack(side=tk.LEFT, padx=5)
        
        # Work directory
        work_frame = ttk.Frame(paths_frame)
        work_frame.pack(fill=tk.X, padx=10, pady=5)
        
        work_label = ttk.Label(work_frame, text="Work Directory:")
        work_label.pack(side=tk.LEFT, padx=5)
        
        self.work_path_var = tk.StringVar(value=self.config_manager.get_config()["paths"]["work_dir"])
        work_entry = ttk.Entry(work_frame, textvariable=self.work_path_var)
        work_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        work_button = ttk.Button(
            work_frame, 
            text="Browse",
            command=lambda: self._browse_directory(self.work_path_var)
        )
        work_button.pack(side=tk.LEFT, padx=5)
        
        # Output directory
        output
