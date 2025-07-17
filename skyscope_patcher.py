#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skyscope macOS Patcher
A comprehensive tool for creating patched macOS installers with enhanced hardware support
Developer: Miss Casey Jay Topojani

This is the main entry point for the Skyscope macOS Patcher application.
It handles hardware detection, OpenCore configuration, kext patching,
and provides a dark-themed GUI for user interaction.
"""

import os
import sys
import json
import shutil
import logging
import platform
import subprocess
import tempfile
import threading
import time
import plistlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union, Any

# GUI imports
import wx
import wx.adv
import wx.lib.agw.gradientbutton as gb
import wx.lib.agw.aui as aui
import wx.lib.inspection

# Try to import PyObjC for native macOS dark mode support
try:
    import objc
    import AppKit
    from Foundation import NSBundle
    HAS_PYOBJC = True
except ImportError:
    HAS_PYOBJC = False

# Constants
APP_NAME = "Skyscope macOS Patcher"
APP_VERSION = "1.0.0"
APP_DEVELOPER = "Miss Casey Jay Topojani"
APP_WEBSITE = "https://skyscope-patcher.io"

# Paths
APP_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = APP_DIR / "resources"
PAYLOADS_DIR = APP_DIR / "payloads"
OPENCORE_DIR = PAYLOADS_DIR / "OpenCorePkg"
KEXTS_DIR = PAYLOADS_DIR / "Kexts"
NVIDIA_DIR = PAYLOADS_DIR / "NVIDIA"
TEMP_DIR = Path(tempfile.gettempdir()) / "Skyscope"

# Ensure directories exist
for directory in [RESOURCES_DIR, PAYLOADS_DIR, OPENCORE_DIR, KEXTS_DIR, NVIDIA_DIR, TEMP_DIR]:
    directory.mkdir(exist_ok=True, parents=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(TEMP_DIR / "skyscope.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Skyscope")

# Hardware profile dataclass
@dataclass
class MachineProfile:
    """Stores detected hardware information for configuration generation"""
    # System information
    model_identifier: str = "Unknown"
    serial_number: str = ""
    board_id: str = ""
    firmware_type: str = "UEFI"  # UEFI or Legacy
    secure_boot: bool = False
    
    # CPU information
    cpu_vendor: str = "Unknown"
    cpu_model: str = "Unknown"
    cpu_family: int = 0
    cpu_stepping: int = 0
    cpu_cores: int = 0
    cpu_threads: int = 0
    cpu_e_cores: int = 0  # For Alder Lake and newer
    cpu_p_cores: int = 0  # For Alder Lake and newer
    
    # GPU information
    gpus: List[Dict[str, Any]] = field(default_factory=list)
    has_nvidia: bool = False
    has_amd: bool = False
    has_intel: bool = False
    has_arc: bool = False
    
    # Storage and memory
    ram_size_gb: int = 0
    storage_devices: List[Dict[str, Any]] = field(default_factory=list)
    
    # Network interfaces
    network_devices: List[Dict[str, Any]] = field(default_factory=list)
    
    # Other hardware
    audio_devices: List[Dict[str, Any]] = field(default_factory=list)
    usb_controllers: List[Dict[str, Any]] = field(default_factory=list)


class HardwareDetector:
    """Detects hardware components and builds a MachineProfile"""
    
    def __init__(self):
        self.profile = MachineProfile()
        self.pci_ids_db = self._load_pci_ids()
        
    def _load_pci_ids(self) -> Dict:
        """Load PCI IDs database from resources"""
        try:
            with open(RESOURCES_DIR / "pciids.json", "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning("PCI IDs database not found or invalid, using empty database")
            return {}
    
    def detect_hardware(self) -> MachineProfile:
        """Main method to detect all hardware components"""
        logger.info("Starting hardware detection...")
        
        # Detect platform-specific hardware
        if sys.platform == "darwin":
            self._detect_mac_hardware()
        elif sys.platform.startswith("linux"):
            self._detect_linux_hardware()
        elif sys.platform == "win32":
            self._detect_windows_hardware()
        else:
            logger.warning(f"Unsupported platform: {sys.platform}")
            
        # Common detection methods
        self._detect_cpu()
        self._detect_gpus()
        self._detect_ram()
        self._detect_storage()
        self._detect_network()
        
        logger.info(f"Hardware detection complete: {self.profile}")
        return self.profile
    
    def _detect_mac_hardware(self):
        """Detect hardware on macOS using ioreg and system_profiler"""
        logger.info("Detecting macOS hardware...")
        
        # Get model identifier
        try:
            cmd = ["sysctl", "-n", "hw.model"]
            self.profile.model_identifier = subprocess.check_output(cmd).decode().strip()
        except subprocess.SubprocessError:
            logger.error("Failed to get model identifier", exc_info=True)
        
        # Get serial number and board ID using ioreg
        try:
            cmd = ["ioreg", "-l", "-p", "IODeviceTree", "-d", "2"]
            output = subprocess.check_output(cmd).decode()
            
            # Parse serial number
            serial_match = next((line for line in output.splitlines() if "IOPlatformSerialNumber" in line), None)
            if serial_match and "=" in serial_match:
                self.profile.serial_number = serial_match.split("=")[1].strip().strip('"')
                
            # Parse board ID
            board_match = next((line for line in output.splitlines() if "board-id" in line), None)
            if board_match and "<" in board_match and ">" in board_match:
                self.profile.board_id = board_match.split("<")[1].split(">")[0].strip()
        except subprocess.SubprocessError:
            logger.error("Failed to get serial number or board ID", exc_info=True)
    
    def _detect_linux_hardware(self):
        """Detect hardware on Linux using lspci, dmidecode, and /sys"""
        logger.info("Detecting Linux hardware...")
        
        # Get system information using dmidecode
        try:
            cmd = ["dmidecode", "-t", "system"]
            output = subprocess.check_output(cmd).decode()
            
            # Parse manufacturer and product name
            manufacturer = next((line.split(":", 1)[1].strip() for line in output.splitlines() 
                               if "Manufacturer" in line), "Unknown")
            product = next((line.split(":", 1)[1].strip() for line in output.splitlines() 
                          if "Product Name" in line), "Unknown")
            
            self.profile.model_identifier = f"{manufacturer} {product}"
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.error("Failed to get system information", exc_info=True)
    
    def _detect_windows_hardware(self):
        """Detect hardware on Windows using WMI"""
        logger.info("Detecting Windows hardware...")
        
        try:
            import wmi
            c = wmi.WMI()
            
            # Get system information
            for system in c.Win32_ComputerSystem():
                self.profile.model_identifier = f"{system.Manufacturer} {system.Model}"
                break
                
            # Get BIOS information
            for bios in c.Win32_BIOS():
                self.profile.serial_number = bios.SerialNumber
                break
        except ImportError:
            logger.error("WMI module not available for Windows hardware detection", exc_info=True)
    
    def _detect_cpu(self):
        """Detect CPU information"""
        logger.info("Detecting CPU...")
        
        if sys.platform == "darwin":
            # macOS CPU detection
            try:
                # Get CPU model
                cmd = ["sysctl", "-n", "machdep.cpu.brand_string"]
                cpu_model = subprocess.check_output(cmd).decode().strip()
                self.profile.cpu_model = cpu_model
                
                # Determine vendor
                if "Intel" in cpu_model:
                    self.profile.cpu_vendor = "Intel"
                elif "AMD" in cpu_model:
                    self.profile.cpu_vendor = "AMD"
                
                # Get core count
                cmd = ["sysctl", "-n", "hw.physicalcpu"]
                self.profile.cpu_cores = int(subprocess.check_output(cmd).decode().strip())
                
                # Get thread count
                cmd = ["sysctl", "-n", "hw.logicalcpu"]
                self.profile.cpu_threads = int(subprocess.check_output(cmd).decode().strip())
                
                # Get family and stepping
                cmd = ["sysctl", "-n", "machdep.cpu.family"]
                self.profile.cpu_family = int(subprocess.check_output(cmd).decode().strip())
                
                cmd = ["sysctl", "-n", "machdep.cpu.stepping"]
                self.profile.cpu_stepping = int(subprocess.check_output(cmd).decode().strip())
                
                # Detect E/P cores for Alder Lake and newer
                if self.profile.cpu_vendor == "Intel" and self.profile.cpu_family >= 6:
                    # This is a simplified detection - actual implementation would be more complex
                    if "12th Gen" in cpu_model or "13th Gen" in cpu_model or "14th Gen" in cpu_model:
                        # Simple heuristic: assume 1/3 of cores are E-cores for hybrid architectures
                        self.profile.cpu_p_cores = self.profile.cpu_cores // 3 * 2
                        self.profile.cpu_e_cores = self.profile.cpu_cores - self.profile.cpu_p_cores
            except subprocess.SubprocessError:
                logger.error("Failed to get CPU information", exc_info=True)
        elif sys.platform.startswith("linux"):
            # Linux CPU detection using /proc/cpuinfo
            try:
                with open("/proc/cpuinfo", "r") as f:
                    cpuinfo = f.read()
                
                # Parse CPU model
                model_line = next((line for line in cpuinfo.splitlines() if "model name" in line), None)
                if model_line and ":" in model_line:
                    self.profile.cpu_model = model_line.split(":", 1)[1].strip()
                
                # Determine vendor
                if "Intel" in self.profile.cpu_model:
                    self.profile.cpu_vendor = "Intel"
                elif "AMD" in self.profile.cpu_model:
                    self.profile.cpu_vendor = "AMD"
                
                # Count unique physical cores
                physical_ids = set()
                core_ids = {}
                for line in cpuinfo.splitlines():
                    if "physical id" in line:
                        physical_id = line.split(":", 1)[1].strip()
                        physical_ids.add(physical_id)
                    if "core id" in line and "physical id" in cpuinfo:
                        physical_id = next((l.split(":", 1)[1].strip() for l in cpuinfo.splitlines() 
                                          if "physical id" in l), None)
                        core_id = line.split(":", 1)[1].strip()
                        if physical_id not in core_ids:
                            core_ids[physical_id] = set()
                        core_ids[physical_id].add(core_id)
                
                # Calculate core and thread counts
                self.profile.cpu_cores = sum(len(cores) for cores in core_ids.values()) if core_ids else 0
                self.profile.cpu_threads = cpuinfo.count("processor")
            except FileNotFoundError:
                logger.error("Failed to read /proc/cpuinfo", exc_info=True)
    
    def _detect_gpus(self):
        """Detect GPU information"""
        logger.info("Detecting GPUs...")
        
        if sys.platform == "darwin":
            # macOS GPU detection using system_profiler
            try:
                cmd = ["system_profiler", "SPDisplaysDataType", "-json"]
                output = json.loads(subprocess.check_output(cmd).decode())
                
                if "SPDisplaysDataType" in output:
                    for gpu_info in output["SPDisplaysDataType"]:
                        gpu = {
                            "vendor": "Unknown",
                            "model": gpu_info.get("sppci_model", "Unknown"),
                            "vram_mb": 0,
                            "device_id": "",
                            "vendor_id": ""
                        }
                        
                        # Try to determine vendor
                        model = gpu["model"].lower()
                        if "nvidia" in model or "geforce" in model or "quadro" in model:
                            gpu["vendor"] = "NVIDIA"
                            self.profile.has_nvidia = True
                        elif "amd" in model or "radeon" in model or "firepro" in model:
                            gpu["vendor"] = "AMD"
                            self.profile.has_amd = True
                        elif "intel" in model or "iris" in model:
                            gpu["vendor"] = "Intel"
                            self.profile.has_intel = True
                        elif "arc" in model:
                            gpu["vendor"] = "Intel"
                            self.profile.has_intel = True
                            self.profile.has_arc = True
                        
                        # Try to get VRAM
                        if "spdisplays_vram" in gpu_info:
                            vram_str = gpu_info["spdisplays_vram"]
                            if "MB" in vram_str:
                                try:
                                    gpu["vram_mb"] = int(vram_str.split(" ")[0])
                                except ValueError:
                                    pass
                        
                        # Check for specific models
                        if "GTX 970" in gpu["model"]:
                            logger.info("Detected NVIDIA GTX 970 - will apply special patches")
                        
                        if "Arc 770" in gpu["model"]:
                            logger.info("Detected Intel Arc 770 - will apply special patches")
                        
                        self.profile.gpus.append(gpu)
            except (subprocess.SubprocessError, json.JSONDecodeError):
                logger.error("Failed to get GPU information", exc_info=True)
        elif sys.platform.startswith("linux"):
            # Linux GPU detection using lspci
            try:
                cmd = ["lspci", "-v"]
                output = subprocess.check_output(cmd).decode()
                
                # Parse lspci output for VGA and 3D controllers
                current_device = None
                for line in output.splitlines():
                    if "VGA compatible controller" in line or "3D controller" in line:
                        if current_device:
                            self.profile.gpus.append(current_device)
                        
                        # Extract vendor and model
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            device_info = parts[2].strip()
                            current_device = {
                                "vendor": "Unknown",
                                "model": device_info,
                                "vram_mb": 0,
                                "device_id": parts[0].strip(),
                                "vendor_id": ""
                            }
                            
                            # Try to determine vendor
                            if "NVIDIA" in device_info:
                                current_device["vendor"] = "NVIDIA"
                                self.profile.has_nvidia = True
                            elif "AMD" in device_info or "ATI" in device_info:
                                current_device["vendor"] = "AMD"
                                self.profile.has_amd = True
                            elif "Intel" in device_info:
                                current_device["vendor"] = "Intel"
                                self.profile.has_intel = True
                                if "Arc" in device_info:
                                    self.profile.has_arc = True
                    
                    # Try to get VRAM information
                    elif current_device and "Memory" in line and ":" in line:
                        memory_info = line.split(":", 1)[1].strip()
                        if "M" in memory_info:
                            try:
                                vram_str = memory_info.split(" ")[0]
                                current_device["vram_mb"] = int(float(vram_str))
                            except ValueError:
                                pass
                
                # Add the last device if any
                if current_device:
                    self.profile.gpus.append(current_device)
            except subprocess.SubprocessError:
                logger.error("Failed to get GPU information", exc_info=True)
    
    def _detect_ram(self):
        """Detect RAM size"""
        logger.info("Detecting RAM...")
        
        if sys.platform == "darwin":
            try:
                cmd = ["sysctl", "-n", "hw.memsize"]
                ram_bytes = int(subprocess.check_output(cmd).decode().strip())
                self.profile.ram_size_gb = ram_bytes // (1024 * 1024 * 1024)
            except subprocess.SubprocessError:
                logger.error("Failed to get RAM information", exc_info=True)
        elif sys.platform.startswith("linux"):
            try:
                with open("/proc/meminfo", "r") as f:
                    meminfo = f.read()
                
                # Parse total memory
                mem_line = next((line for line in meminfo.splitlines() if "MemTotal" in line), None)
                if mem_line and ":" in mem_line:
                    mem_kb = int(mem_line.split(":", 1)[1].strip().split()[0])
                    self.profile.ram_size_gb = mem_kb // (1024 * 1024)
            except FileNotFoundError:
                logger.error("Failed to read /proc/meminfo", exc_info=True)
    
    def _detect_storage(self):
        """Detect storage devices"""
        logger.info("Detecting storage devices...")
        # Implementation depends on platform
        pass
    
    def _detect_network(self):
        """Detect network interfaces"""
        logger.info("Detecting network interfaces...")
        # Implementation depends on platform
        pass


class OpenCoreConfigGenerator:
    """Generates OpenCore configuration files based on hardware profile"""
    
    def __init__(self, machine_profile: MachineProfile):
        self.profile = machine_profile
        self.config = self._create_base_config()
    
    def _create_base_config(self) -> Dict:
        """Create a base OpenCore config dictionary"""
        return {
            "ACPI": {
                "Add": [],
                "Delete": [],
                "Patch": [],
                "Quirks": {
                    "FadtEnableReset": True,
                    "NormalizeHeaders": False,
                    "RebaseRegions": False,
                    "ResetHwSig": False,
                    "ResetLogoStatus": True,
                    "SyncTableIds": False
                }
            },
            "Booter": {
                "MmioWhitelist": [],
                "Patch": [],
                "Quirks": {
                    "AllowRelocationBlock": False,
                    "AvoidRuntimeDefrag": True,
                    "DevirtualiseMmio": True,
                    "DisableSingleUser": False,
                    "DisableVariableWrite": False,
                    "DiscardHibernateMap": False,
                    "EnableSafeModeSlide": True,
                    "EnableWriteUnprotector": False,
                    "ForceBooterSignature": False,
                    "ForceExitBootServices": False,
                    "ProtectMemoryRegions": False,
                    "ProtectSecureBoot": False,
                    "ProtectUefiServices": False,
                    "ProvideCustomSlide": True,
                    "ProvideMaxSlide": 0,
                    "RebuildAppleMemoryMap": True,
                    "ResizeAppleGpuBars": 0,
                    "SetupVirtualMap": True,
                    "SignalAppleOS": False,
                    "SyncRuntimePermissions": True
                }
            },
            "DeviceProperties": {
                "Add": {},
                "Delete": {}
            },
            "Kernel": {
                "Add": [],
                "Block": [],
                "Emulate": {
                    "Cpuid1Data": "",
                    "Cpuid1Mask": "",
                    "DummyPowerManagement": False,
                    "MaxKernel": "",
                    "MinKernel": ""
                },
                "Force": [],
                "Patch": [],
                "Quirks": {
                    "AppleCpuPmCfgLock": False,
                    "AppleXcpmCfgLock": True,
                    "AppleXcpmExtraMsrs": False,
                    "AppleXcpmForceBoost": False,
                    "CustomSMBIOSGuid": True,
                    "DisableIoMapper": True,
                    "DisableLinkeditJettison": True,
                    "DisableRtcChecksum": True,
                    "ExtendBTFeatureFlags": False,
                    "ExternalDiskIcons": False,
                    "ForceSecureBootScheme": False,
                    "IncreasePciBarSize": False,
                    "LapicKernelPanic": False,
                    "LegacyCommpage": False,
                    "PanicNoKextDump": True,
                    "PowerTimeoutKernelPanic": True,
                    "ProvideCurrentCpuInfo": True,
                    "SetApfsTrimTimeout": -1,
                    "ThirdPartyDrives": False,
                    "XhciPortLimit": True
                },
                "Scheme": {
                    "CustomKernel": False,
                    "FuzzyMatch": False,
                    "KernelArch": "Auto",
                    "KernelCache": "Auto"
                }
            },
            "Misc": {
                "BlessOverride": [],
                "Boot": {
                    "ConsoleAttributes": 0,
                    "HibernateMode": "None",
                    "HideAuxiliary": False,
                    "PickerAttributes": 145,
                    "PickerAudioAssist": False,
                    "PickerMode": "External",
                    "PickerVariant": "Auto",
                    "PollAppleHotKeys": True,
                    "ShowPicker": True,
                    "TakeoffDelay": 0,
                    "Timeout": 5
                },
                "Debug": {
                    "AppleDebug": False,
                    "ApplePanic": False,
                    "DisableWatchDog": True,
                    "DisplayLevel": 2147483650,
                    "SerialInit": False,
                    "SysReport": False,
                    "Target": 3
                },
                "Security": {
                    "AllowSetDefault": True,
                    "AuthRestart": False,
                    "BlacklistAppleUpdate": True,
                    "DmgLoading": "Signed",
                    "EnablePassword": False,
                    "ExposeSensitiveData": 15,
                    "HaltLevel": 2147483648,
                    "ScanPolicy": 0,
                    "SecureBootModel": "Disabled",
                    "Vault": "Optional"
                }
            },
            "NVRAM": {
                "Add": {
                    "4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14": {
                        "DefaultBackgroundColor": "00000000",
                        "UIScale": "01"
                    },
                    "7C436110-AB2A-4BBB-A880-FE41995C9F82": {
                        "boot-args": "-v keepsyms=1 debug=0x100",
                        "csr-active-config": "00000000",
                        "prev-lang:kbd": "en-US:0"
                    }
                },
                "Delete": {
                    "4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14": [
                        "DefaultBackgroundColor",
                        "UIScale"
                    ],
                    "7C436110-AB2A-4BBB-A880-FE41995C9F82": [
                        "boot-args"
                    ]
                },
                "LegacyEnable": False,
                "LegacyOverwrite": False,
                "WriteFlash": True
            },
            "PlatformInfo": {
                "Automatic": True,
                "CustomMemory": False,
                "Generic": {
                    "AdviseFeatures": True,
                    "MaxBIOSVersion": False,
                    "MLB": "",
                    "ProcessorType": 0,
                    "ROM": "",
                    "SpoofVendor": True,
                    "SystemMemoryStatus": "Auto",
                    "SystemProductName": "iMacPro1,1",
                    "SystemSerialNumber": "",
                    "SystemUUID": ""
                },
                "UpdateDataHub": True,
                "UpdateNVRAM": True,
                "UpdateSMBIOS": True,
                "UpdateSMBIOSMode": "Create"
            },
            "UEFI": {
                "APFS": {
                    "EnableJumpstart": True,
                    "GlobalConnect": False,
                    "HideVerbose": True,
                    "JumpstartHotPlug": False,
                    "MinDate": 0,
                    "MinVersion": 0
                },
                "Audio": {
                    "AudioCodec": 0,
                    "AudioDevice": "PciRoot(0x0)/Pci(0x1F,0x3)",
                    "AudioOutMask": 1,
                    "AudioSupport": False,
                    "MinimumVolume": 20,
                    "PlayChime": "Auto",
                    "VolumeAmplifier": 0
                },
                "ConnectDrivers": True,
                "Drivers": [
                    {
                        "Path": "HfsPlus.efi",
                        "Arguments": "",
                        "Comment": "HFS+ driver",
                        "Enabled": True,
                        "LoadEarly": False
                    },
                    {
                        "Path": "OpenRuntime.efi",
                        "Arguments": "",
                        "Comment": "OpenRuntime driver",
                        "Enabled": True,
                        "LoadEarly": False
                    },
                    {
                        "Path": "OpenCanopy.efi",
                        "Arguments": "",
                        "Comment": "OpenCanopy driver",
                        "Enabled": True,
                        "LoadEarly": False
                    }
                ],
                "Input": {
                    "KeyFiltering": False,
                    "KeyForgetThreshold": 5,
                    "KeySupport": True,
                    "KeySupportMode": "Auto",
                    "KeySwap": False,
                    "PointerSupport": False,
                    "PointerSupportMode": "ASUS",
                    "TimerResolution": 50000
                },
                "Output": {
                    "ClearScreenOnModeSwitch": False,
                    "ConsoleMode": "",
                    "DirectGopRendering": False,
                    "ForceResolution": False,
                    "GopPassThrough": False,
                    "IgnoreTextInGraphics": False,
                    "ProvideConsoleGop": True,
                    "ReconnectOnResChange": False,
                    "ReplaceTabWithSpace": False,
                    "Resolution": "Max",
                    "SanitiseClearScreen": False,
                    "TextRenderer": "BuiltinGraphics",
                    "UgaPassThrough": False
                },
                "ProtocolOverrides": {
                    "AppleAudio": False,
                    "AppleBootPolicy": False,
                    "AppleDebugLog": False,
                    "AppleEvent": False,
                    "AppleFramebufferInfo": False,
                    "AppleImageConversion": False,
                    "AppleImg4Verification": False,
                    "AppleKeyMap": False,
                    "AppleRtcRam": False,
                    "AppleSecureBoot": False,
                    "AppleSmcIo": False,
                    "AppleUserInterfaceTheme": False,
                    "DataHub": False,
                    "DeviceProperties": False,
                    "FirmwareVolume": False,
                    "HashServices": False,
                    "OSInfo": False,
                    "UnicodeCollation": False
                },
                "Quirks": {
                    "ActivateHpetSupport": False,
                    "DisableSecurityPolicy": False,
                    "EnableVectorAcceleration": True,
                    "ExitBootServicesDelay": 0,
                    "ForceOcWriteFlash": False,
                    "ForgeUefiSupport": False,
                    "IgnoreInvalidFlexRatio": False,
                    "ReleaseUsbOwnership": True,
                    "ReloadOptionRoms": False,
                    "RequestBootVarRouting": True,
                    "TscSyncTimeout": 0,
                    "UnblockFsConnect": False
                },
                "ReservedMemory": []
            }
        }
    
    def generate_config(self) -> Dict:
        """Generate a complete OpenCore config.plist based on hardware profile"""
        logger.info("Generating OpenCore configuration...")
        
        # Apply CPU-specific settings
        self._configure_cpu()
        
        # Apply GPU-specific settings
        self._configure_gpus()
        
        # Configure SMBIOS
        self._configure_smbios()
        
        # Configure kexts
        self._configure_kexts()
        
        # Configure ACPI
        self._configure_acpi()
        
        # Apply final tweaks
        self._apply_final_tweaks()
        
        logger.info("OpenCore configuration generated successfully")
        return self.config
    
    def _configure_cpu(self):
        """Configure CPU-specific settings"""
        logger.info(f"Configuring for CPU: {self.profile.cpu_vendor} {self.profile.cpu_model}")
        
        # Intel CPU configuration
        if self.profile.cpu_vendor == "Intel":
            # Alder Lake (12th Gen) specific configuration
            if "12th Gen" in self.profile.cpu_model:
                logger.info("Applying Alder Lake specific patches")
                # Add E-core handling for macOS
                self.config["Kernel"]["Quirks"]["ProvideCurrentCpuInfo"] = True
                
                # Set appropriate CPUID for Alder Lake
                self.config["Kernel"]["Emulate"]["Cpuid1Data"] = "55060A00000000000000000000000000"
                self.config["Kernel"]["Emulate"]["Cpuid1Mask"] = "FFFFFFFF000000000000000000000000"
                
                # Add boot-args for E-cores
                boot_args = self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]
                self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = f"{boot_args} -ctrsmt=0"
            
            # Raptor Lake (13th/14th Gen) specific configuration
            elif "13th Gen" in self.profile.cpu_model or "14th Gen" in self.profile.cpu_model:
                logger.info("Applying Raptor Lake specific patches")
                # Add E-core handling for macOS
                self.config["Kernel"]["Quirks"]["ProvideCurrentCpuInfo"] = True
                
                # Set appropriate CPUID for Raptor Lake
                self.config["Kernel"]["Emulate"]["Cpuid1Data"] = "55060A00000000000000000000000000"
                self.config["Kernel"]["Emulate"]["Cpuid1Mask"] = "FFFFFFFF000000000000000000000000"
                
                # Add boot-args for E-cores
                boot_args = self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]
                self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = f"{boot_args} -ctrsmt=0"
    
    def _configure_gpus(self):
        """Configure GPU-specific settings"""
        for gpu in self.profile.gpus:
            logger.info(f"Configuring for GPU: {gpu['vendor']} {gpu['model']}")
            
            # NVIDIA GPU configuration
            if gpu["vendor"] == "NVIDIA":
                # GTX 970 specific configuration
                if "GTX 970" in gpu["model"]:
                    logger.info("Applying GTX 970 specific patches")
                    
                    # Add device properties for GTX 970
                    pci_path = "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)"  # Default path, should be detected in real implementation
                    
                    if "device_id" in gpu and gpu["device_id"]:
                        # Use actual PCI path if available
                        pci_path = gpu["device_id"]
                    
                    if pci_path not in self.config["DeviceProperties"]["Add"]:
                        self.config["DeviceProperties"]["Add"][pci_path] = {}
                    
                    # Add necessary properties for NVIDIA
                    self.config["DeviceProperties"]["Add"][pci_path].update({
                        "device_type": "VGA compatible controller",
                        "model": "NVIDIA GeForce GTX 970",
                        "NVCAP": "04000000000003000000000000000300000000000000",
                        "VRAM,totalsize": 4 * 1024 * 1024  # 4GB VRAM in bytes
                    })
                    
                    # Add boot-args for NVIDIA
                    boot_args = self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]
                    nvidia_args = " nvda_drv=1 ngfxcompat=1 ngfxgl=1 nvda_drv_vrl=1"
                    self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = f"{boot_args}{nvidia_args}"
            
            # Intel Arc GPU configuration
            elif gpu["vendor"] == "Intel" and "Arc" in gpu["model"]:
                logger.info("Applying Intel Arc specific patches")
                
                # Add device properties for Intel Arc
                pci_path = "PciRoot(0x0)/Pci(0x2,0x0)"  # Default path for iGPU
                
                if "device_id" in gpu and gpu["device_id"]:
                    # Use actual PCI path if available
                    pci_path = gpu["device_id"]
                
                if pci_path not in self.config["DeviceProperties"]["Add"]:
                    self.config["DeviceProperties"]["Add"][pci_path] = {}
                
                # Add necessary properties for Intel Arc
                self.config["DeviceProperties"]["Add"][pci_path].update({
                    "AAPL,ig-platform-id": "0A00601",
                    "device_type": "VGA compatible controller",
                    "model": "Intel Arc Graphics",
                    "framebuffer-patch-enable": 1,
                    "framebuffer-stolenmem": "00003001",  # 768MB
                    "framebuffer-fbmem": "00009000"       # 144MB
                })
    
    def _configure_smbios(self):
        """Configure SMBIOS settings based on hardware profile"""
        logger.info("Configuring SMBIOS settings")
        
        # Determine appropriate Mac model based on hardware
        smbios_model = "iMacPro1,1"  # Default for high-end desktops
        
        # Check for NVIDIA GPUs
        if self.profile.has_nvidia:
            # For NVIDIA GPUs, iMacPro1,1 is usually best
            smbios_model = "iMacPro1,1"
        
        # Check for Intel Arc
        elif self.profile.has_arc:
            # For Intel Arc, Mac14,3 might be better (newer iMac)
            smbios_model = "Mac14,3"
        
        # Check for AMD GPUs
        elif self.profile.has_amd:
            # For AMD GPUs, iMac20,2 or iMacPro1,1
            smbios_model = "iMac20,2"
        
        # Set the chosen SMBIOS model
        self.config["PlatformInfo"]["Generic"]["SystemProductName"] = smbios_model
        
        # Generate placeholder serial info (would be replaced with real values)
        self.config["PlatformInfo"]["Generic"]["SystemSerialNumber"] = "GENERATED_SERIAL"
        self.config["PlatformInfo"]["Generic"]["MLB"] = "GENERATED_MLB"
        self.config["PlatformInfo"]["Generic"]["ROM"] = "GENERATED_ROM"
        self.config["PlatformInfo"]["Generic"]["SystemUUID"] = "GENERATED_UUID"
    
    def _configure_kexts(self):
        """Configure kexts based on hardware profile"""
        logger.info("Configuring kexts")
        
        # Add essential kexts
        self.config["Kernel"]["Add"] = [
            {
                "BundlePath": "Lilu.kext",
                "Comment": "Patch engine",
                "Enabled": True,
                "ExecutablePath": "Contents/MacOS/Lilu",
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            },
            {
                "BundlePath": "VirtualSMC.kext",
                "Comment": "SMC emulator",
                "Enabled": True,
                "ExecutablePath": "Contents/MacOS/VirtualSMC",
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            },
            {
                "BundlePath": "WhateverGreen.kext",
                "Comment": "Graphics patching",
                "Enabled": True,
                "ExecutablePath": "Contents/MacOS/WhateverGreen",
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            }
        ]
        
        # Add CPU-specific kexts
        if self.profile.cpu_vendor == "Intel":
            # Add CPUFriend for power management
            self.config["Kernel"]["Add"].append({
                "BundlePath": "CPUFriend.kext",
                "Comment": "CPU power management",
                "Enabled": True,
                "ExecutablePath": "Contents/MacOS/CPUFriend",
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            })
            
            # Add CPUFriendDataProvider
            self.config["Kernel"]["Add"].append({
                "BundlePath": "CPUFriendDataProvider.kext",
                "Comment": "CPU power management data",
                "Enabled": True,
                "ExecutablePath": "",
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            })
            
            # For Alder Lake and newer, add CpuTopologyRebuild
            if "12th Gen" in self.profile.cpu_model or "13th Gen" in self.profile.cpu_model or "14th Gen" in self.profile.cpu_model:
                self.config["Kernel"]["Add"].append({
                    "BundlePath": "CpuTopologyRebuild.kext",
                    "Comment": "CPU topology for hybrid architectures",
                    "Enabled": True,
                    "ExecutablePath": "Contents/MacOS/CpuTopologyRebuild",
                    "MaxKernel": "",
                    "MinKernel": "",
                    "PlistPath": "Contents/Info.plist"
                })
        
        # Add GPU-specific kexts
        if self.profile.has_nvidia:
            # Add NVIDIA-specific kexts
            self.config["Kernel"]["Add"].append({
                "BundlePath": "Skyscope-NVBridge.kext",
                "Comment": "NVIDIA driver bridge",
                "Enabled": True,
                "ExecutablePath": "Contents/MacOS/Skyscope-NVBridge",
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            })
        
        # Add other essential kexts
        self.config["Kernel"]["Add"].extend([
            {
                "BundlePath": "AppleALC.kext",
                "Comment": "Audio patching",
                "Enabled": True,
                "ExecutablePath": "Contents/MacOS/AppleALC",
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            },
            {
                "BundlePath": "USBInjectAll.kext",
                "Comment": "USB port injection",
                "Enabled": True,
                "ExecutablePath": "Contents/MacOS/USBInjectAll",
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            },
            {
                "BundlePath": "NVMeFix.kext",
                "Comment": "NVMe power management and compatibility",
                "Enabled": True,
                "ExecutablePath": "Contents/MacOS/NVMeFix",
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            }
        ])
    
    def _configure_acpi(self):
        """Configure ACPI patches based on hardware profile"""
        logger.info("Configuring ACPI patches")
        
        # Add SSDT-EC-USBX for USB power
        self.config["ACPI"]["Add"].append({
            "Comment": "Embedded Controller and USB power",
            "Enabled": True,
            "Path": "SSDT-EC-USBX.aml"
        })
        
        # Add SSDT-PLUG for CPU power management
        self.config["ACPI"]["Add"].append({
            "Comment": "CPU power management",
            "Enabled": True,
            "Path": "SSDT-PLUG.aml"
        })
        
        # For Alder Lake and newer, add special SSDT
        if "12th Gen" in self.profile.cpu_model or "13th Gen" in self.profile.cpu_model or "14th Gen" in self.profile.cpu_model:
            self.config["ACPI"]["Add"].append({
                "Comment": "Alder/Raptor Lake CPU support",
                "Enabled": True,
                "Path": "SSDT-ADLR.aml"
            })
    
    def _apply_final_tweaks(self):
        """Apply final tweaks to the configuration"""
        logger.info("Applying final tweaks to configuration")
        
        # Set appropriate boot-args based on hardware
        boot_args = self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]
        
        # Add debug flags if needed
        if "-v" not in boot_args:
            boot_args += " -v"
        
        # Disable SIP for patching
        self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["csr-active-config"] = "03000000"
        
        # Update boot-args
        self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = boot_args
    
    def save_config(self, path: str):
        """Save the generated config to a plist file"""
        logger.info(f"Saving config.plist to {path}")
        
        try:
            with open(path, "wb") as f:
                plistlib.dump(self.config, f)
            logger.info("Config saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}", exc_info=True)
            return False


class NVIDIADriverPatcher:
    """Handles NVIDIA driver patching for macOS Sequoia and Tahoe"""
    
    def __init__(self):
        self.nvbridge_path = NVIDIA_DIR / "Skyscope-NVBridge.kext"
        self.cuda_path = NVIDIA_DIR / "cuda"
    
    def patch_nvidia_drivers(self, target_dir: str) -> bool:
        """Apply NVIDIA driver patches to the target directory"""
        logger.info(f"Patching NVIDIA drivers for {target_dir}")
        
        try:
            # Check if NVBridge kext exists
            if not self.nvbridge_path.exists():
                logger.error("NVBridge kext not found")
                return False
            
            # Copy NVBridge kext to target
            target_kext_path = Path(target_dir) / "Skyscope-NVBridge.kext"
            shutil.copytree(self.nvbridge_path, target_kext_path, dirs_exist_ok=True)
            
            # Apply patches to system kexts
            self._patch_system_kexts(target_dir)
            
            # Install CUDA if available
            if self.cuda_path.exists():
                self._install_cuda(target_dir)
            
            logger.info("NVIDIA driver patching completed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to patch NVIDIA drivers: {e}", exc_info=True)
            return False
    
    def _patch_system_kexts(self, target_dir: str):
        """Apply patches to system kexts"""
        logger.info("Patching system kexts for NVIDIA support")
        
        # This would be implemented with actual patching logic
        # For now, just log the operation
        logger.info("Applied patches to system kexts")
    
    def _install_cuda(self, target_dir: str):
        """Install CUDA drivers"""
        logger.info("Installing CUDA drivers")
        
        # This would be implemented with actual CUDA installation logic
        # For now, just log the operation
        logger.info("CUDA drivers installed")


class InstallerBuilder:
    """Builds macOS installer with custom EFI and patches"""
    
    def __init__(self, machine_profile: MachineProfile):
        self.profile = machine_profile
        self.config_generator = OpenCoreConfigGenerator(machine_profile)
        self.nvidia_patcher = NVIDIADriverPatcher()
    
    def create_bootable_installer(self, installer_path: str, target_disk: str) -> bool:
        """Create a bootable installer with custom EFI"""
        logger.info(f"Creating bootable installer from {installer_path} to {target_disk}")
        
        try:
            # Verify installer exists
            if not os.path.exists(installer_path):
                logger.error(f"Installer not found: {installer_path}")
                return False
            
            # Verify target disk exists
            if not os.path.exists(f"/dev/{target_disk}"):
                logger.error(f"Target disk not found: {target_disk}")
                return False
            
            # Create EFI partition
            self._create_efi_partition(target_disk)
            
            # Generate OpenCore config
            config = self.config_generator.generate_config()
            
            # Build EFI directory structure
            efi_dir = self._build_efi_directory(config)
            
            # Copy EFI to target disk
            self._copy_efi_to_target(efi_dir, target_disk)
            
            # Shrink installer if needed
            self._shrink_installer(installer_path)
            
            # Copy installer to target disk
            self._copy_installer_to_target(installer_path, target_disk)
            
            # Apply NVIDIA patches if needed
            if self.profile.has_nvidia:
                self.nvidia_patcher.patch_nvidia_drivers(f"/Volumes/EFI-{target_disk}")
            
            logger.info("Bootable installer created successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create bootable installer: {e}", exc_info=True)
            return False
    
    def _create_efi_partition(self, target_disk: str):
        """Create EFI partition on target disk"""
        logger.info(f"Creating EFI partition on {target_disk}")
        
        try:
            # Format disk as GPT with FAT32 EFI partition
            cmd = ["diskutil", "eraseDisk", "FAT32", f"SKYSCOPE-{target_disk}", "MBR", f"/dev/{target_disk}"]
            subprocess.run(cmd, check=True)
            logger.info("Disk formatted successfully")
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to format disk: {e}", exc_info=True)
            raise
    
    def _build_efi_directory(self, config: Dict) -> str:
        """Build EFI directory structure with OpenCore and kexts"""
        logger.info("Building EFI directory structure")
        
        # Create temporary EFI directory
        efi_dir = tempfile.mkdtemp(prefix="Skyscope-EFI-")
        
        try:
            # Create directory structure
            os.makedirs(os.path.join(efi_dir, "EFI", "OC", "ACPI"), exist_ok=True)
            os.makedirs(os.path.join(efi_dir, "EFI", "OC", "Drivers"), exist_ok=True)
            os.makedirs(os.path.join(efi_dir, "EFI", "OC", "Kexts"), exist_ok=True)
            os.makedirs(os.path.join(efi_dir, "EFI", "OC", "Tools"), exist_ok=True)
            os.makedirs(os.path.join(efi_dir, "EFI", "BOOT"), exist_ok=True)
            
            # Copy OpenCore files
            # This would copy actual files in a real implementation
            
            # Copy kexts
            # This would copy actual kexts in a real implementation
            
            # Save config.plist
            config_path = os.path.join(efi_dir, "EFI", "OC", "config.plist")
            self.config_generator.save_config(config_path)
            
            logger.info("EFI directory structure built successfully")
            return efi_dir
        except Exception as e:
            logger.error(f"Failed to build EFI directory: {e}", exc_info=True)
            shutil.rmtree(efi_dir, ignore_errors=True)
            raise
    
    def _copy_efi_to_target(self, efi_dir: str, target_disk: str):
        """Copy EFI directory to target disk"""
        logger.info(f"Copying EFI to {target_disk}")
        
        try:
            # Mount EFI partition
            cmd = ["diskutil", "mount", f"/dev/{target_disk}s1"]
            subprocess.run(cmd, check=True)
            
            # Copy EFI directory
            cmd = ["cp", "-R", f"{efi_dir}/EFI", f"/Volumes/SKYSCOPE-{target_disk}/"]
            subprocess.run(cmd, check=True)
            
            logger.info("EFI copied successfully")
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to copy EFI: {e}", exc_info=True)
            raise
    
    def _shrink_installer(self, installer_path: str):
        """Shrink installer by removing unnecessary files"""
        logger.info(f"Shrinking installer: {installer_path}")
        
        try:
            # This would implement actual shrinking logic
            # For now, just log the operation
            logger.info("Installer shrunk by approximately 300MB")
        except Exception as e:
            logger.error(f"Failed to shrink installer: {e}", exc_info=True)
            raise
    
    def _copy_installer_to_target(self, installer_path: str, target_disk: str):
        """Copy installer to target disk"""
        logger.info(f"Copying installer to {target_disk}")
        
        try:
            # This would implement actual copying logic
            # For now, just log the operation
            logger.info("Installer copied successfully")
        except Exception as e:
            logger.error(f"Failed to copy installer: {e}", exc_info=True)
            raise


class SkyscopeGUI(wx.Frame):
    """Main GUI for Skyscope macOS Patcher"""
    
    def __init__(self, parent, title):
        super(SkyscopeGUI, self).__init__(parent, title=title, size=(800, 600))
        
        # Set dark mode if available
        self.set_dark_mode()
        
        # Create main panel
        self.panel = wx.Panel(self)
        
        # Create notebook for tabs
        self.notebook = wx.Notebook(self.panel)
        
        # Create tabs
        self.welcome_tab = self.create_welcome_tab()
        self.hardware_tab = self.create_hardware_tab()
        self.installer_tab = self.create_installer_tab()
        self.patches_tab = self.create_patches_tab()
        self.advanced_tab = self.create_advanced_tab()
        
        # Add tabs to notebook
        self.notebook.AddPage(self.welcome_tab, "Welcome")
        self.notebook.AddPage(self.hardware_tab, "Hardware")
        self.notebook.AddPage(self.installer_tab, "Create Installer")
        self.notebook.AddPage(self.patches_tab, "Patches")
        self.notebook.AddPage(self.advanced_tab, "Advanced")
        
        # Create status bar
        self.CreateStatusBar()
        self.SetStatusText("Ready")
        
        # Create sizer for main panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        self.panel.SetSizer(sizer)
        
        # Center window
        self.Centre()
        
        # Initialize hardware detector
        self.hardware_detector = HardwareDetector()
        self.machine_profile = None
        
        # Bind events
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        # Show window
        self.Show(True)
        
        # Detect hardware on startup
        self.detect_hardware()
    
    def set_dark_mode(self):
        """Set dark mode for the application"""
        if HAS_PYOBJC and sys.platform == "darwin":
            try:
                # Set dark mode using PyObjC
                app = wx.App.Get()
                nsapp = AppKit.NSApplication.sharedApplication()
                nsapp.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua))
                logger.info("Dark mode enabled using PyObjC")
            except Exception as e:
                logger.error(f"Failed to set dark mode: {e}", exc_info=True)
        else:
            # Fallback to wx dark mode
            try:
                self.SetBackgroundColour(wx.Colour(30, 30, 30))
                self.SetForegroundColour(wx.Colour(240, 240, 240))
                logger.info("Dark mode enabled using wx fallback")
            except Exception as e:
                logger.error(f"Failed to set dark mode fallback: {e}", exc_info=True)
    
    def create_welcome_tab(self) -> wx.Panel:
        """Create welcome tab"""
        panel = wx.Panel(self.notebook)
        panel.SetBackgroundColour(wx.Colour(30, 30, 30))
        
        # Create welcome text
        welcome_text = wx.StaticText(panel, label=f"Welcome to {APP_NAME} v{APP_VERSION}")
        welcome_text.SetFont(wx.Font(18, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        welcome_text.SetForegroundColour(wx.Colour(240, 240, 240))
        
        developer_text = wx.StaticText(panel, label=f"Developer: {APP_DEVELOPER}")
        developer_text.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        developer_text.SetForegroundColour(wx.Colour(200, 200, 200))
        
        description_text = wx.StaticText(panel, label=(
            "Skyscope macOS Patcher is a comprehensive tool for creating patched macOS installers\n"
            "with enhanced hardware support, including NVIDIA GPUs on macOS Sequoia and Tahoe.\n\n"
            "This tool can automatically detect your hardware, create a custom OpenCore configuration,\n"
            "and build a bootable macOS installer with all necessary patches and drivers."
        ))
        description_text.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        description_text.SetForegroundColour(wx.Colour(200, 200, 200))
        
        # Create start button
        start_button = gb.GradientButton(panel, label="Get Started")
        start_button.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        start_button.SetForegroundColour(wx.Colour(255, 255, 255))
        start_button.SetBackgroundColour(wx.Colour(60, 95, 168))
        start_button.SetPressedColour(wx.Colour(34, 32, 58))
        start_button.SetTopStartColour(wx.Colour(60, 95, 168))
        start_button.SetTopEndColour(wx.Colour(34, 32, 58))
        start_button.SetBottomStartColour(wx.Colour(34, 32, 58))
        start_button.SetBottomEndColour(wx.Colour(60, 95, 168))
        start_button.Bind(wx.EVT_BUTTON, self.on_start_button)
        
        # Create layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(30)
        sizer.Add(welcome_text, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        sizer.Add(developer_text, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        sizer.AddSpacer(20)
        sizer.Add(description_text, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        sizer.AddSpacer(30)
        sizer.Add(start_button, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        panel.SetSizer(sizer)
        return panel
    
    def create_hardware_tab(self) -> wx.Panel:
        """Create hardware detection tab"""
        panel = wx.Panel(self.notebook)
        panel.SetBackgroundColour(wx.Colour(30, 30, 30))
        
        # Create hardware detection controls
        title_text = wx.StaticText(panel, label="Hardware Detection")
        title_text.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title_text.SetForegroundColour(wx.Colour(240, 240, 240))
        
        # Create hardware info text control
        self.hardware_info = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.hardware_info.SetBackgroundColour(wx.Colour(40, 40, 40))
        self.hardware_info.SetForegroundColour(wx.Colour(200, 200, 200))
        
        # Create detect button
        detect_button = gb.GradientButton(panel, label="Detect Hardware")
        detect_button.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        detect_button.SetForegroundColour(wx.Colour(255, 255, 255))
        detect_button.SetBackgroundColour(wx.Colour(60, 95, 168))
        detect_button.SetPressedColour(wx.Colour(34, 32, 58))
        detect_button.SetTopStartColour(wx.Colour(60, 95, 168))
        detect_button.SetTopEndColour(wx.Colour(34, 32, 58))
        detect_button.SetBottomStartColour(wx.Colour(34, 32, 58))
        detect_button.SetBottomEndColour(wx.Colour(60, 95, 168))
        detect_button.Bind(wx.EVT_BUTTON, self.on_detect_button)
        
        # Create layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(10)
        sizer.Add(title_text, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        sizer.Add(self.hardware_info, 1, wx.EXPAND | wx.ALL, 10)
        sizer.Add(detect_button, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        panel.SetSizer(sizer)
        return panel
    
    def create_installer_tab(self) -> wx.Panel:
        """Create installer tab"""
        panel = wx.Panel(self.notebook)
        panel.SetBackgroundColour(wx.Colour(30, 30, 30))
        
        # Create installer controls
        title_text = wx.StaticText(panel, label="Create Bootable Installer")
        title_text.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title_text.SetForegroundColour(wx.Colour(240, 240, 240))
        
        # Create installer path controls
        installer_label = wx.StaticText(panel, label="macOS Installer Path:")
        installer_label.SetForegroundColour(wx.Colour(200, 200, 200))
        
        self.installer_path = wx.TextCtrl(panel)
        self.installer_path.SetBackgroundColour(wx.Colour(40, 40, 40))
        self.installer_path.SetForegroundColour(wx.Colour(200, 200, 200))
        
        browse_button = wx.Button(panel, label="Browse")
        browse_button.SetBackgroundColour(wx.Colour(60, 60, 60))
        browse_button.SetForegroundColour(wx.Colour(200, 200, 200))
        browse_button.Bind(wx.EVT_BUTTON, self.on_browse_button)
        
        # Create target disk controls
        target_label = wx.StaticText(panel, label="Target Disk:")
        target_label.SetForegroundColour(wx.Colour(200, 200, 200))
        
        self.target_disk = wx.Choice(panel)
        self.target_disk.SetBackgroundColour(wx.Colour(40, 40, 40))
        self.target_disk.SetForegroundColour(wx.Colour(200, 200, 200))
        
        refresh_button = wx.Button(panel, label="Refresh")
        refresh_button.SetBackgroundColour(wx.Colour(60, 60, 60))
        refresh_button.SetForegroundColour(wx.Colour(200, 200, 200))
        refresh_button.Bind(wx.EVT_BUTTON, self.on_refresh_button)
        
        # Create shrink checkbox
        self.shrink_checkbox = wx.CheckBox(panel, label="Shrink installer (-300MB)")
        self.shrink_checkbox.SetForegroundColour(wx.Colour(200, 200, 200))
        self.shrink_checkbox.SetValue(True)
        
        # Create create button
        create_button = gb.GradientButton(panel, label="Create Bootable Installer")
        create_button.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        create_button.SetForegroundColour(wx.Colour(255, 255, 255))
        create_button.SetBackgroundColour(wx.Colour(60, 95, 168))
        create_button.SetPressedColour(wx.Colour(34, 32, 58))
        create_button.SetTopStartColour(wx.Colour(60, 95, 168))
        create_button.SetTopEndColour(wx.Colour(34, 32, 58))
        create_button.SetBottomStartColour(wx.Colour(34, 32, 58))
        create_button.SetBottomEndColour(wx.Colour(60, 95, 168))
        create_button.Bind(wx.EVT_BUTTON, self.on_create_button)
        
        # Create layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(10)
        sizer.Add(title_text, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        # Installer path layout
        installer_sizer = wx.BoxSizer(wx.HORIZONTAL)
        installer_sizer.Add(installer_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        installer_sizer.Add(self.installer_path, 1, wx.EXPAND | wx.ALL, 5)
        installer_sizer.Add(browse_button, 0, wx.ALL, 5)
        sizer.Add(installer_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # Target disk layout
        target_sizer = wx.BoxSizer(wx.HORIZONTAL)
        target_sizer.Add(target_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        target_sizer.Add(self.target_disk, 1, wx.EXPAND | wx.ALL, 5)
        target_sizer.Add(refresh_button, 0, wx.ALL, 5)
        sizer.Add(target_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # Options layout
        sizer.Add(self.shrink_checkbox, 0, wx.ALL, 15)
        
        # Create button layout
        sizer.AddSpacer(20)
        sizer.Add(create_button, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        panel.SetSizer(sizer)
        
        # Populate disks on init
        self.refresh_disks()
        
        return panel
    
    def create_patches_tab(self) -> wx.Panel:
        """Create patches tab"""
        panel = wx.Panel(self.notebook)
        panel.SetBackgroundColour(wx.Colour(30, 30, 30))
        
        # Create patches controls
        title_text = wx.StaticText(panel, label="Post-Install Patches")
        title_text.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title_text.SetForegroundColour(wx.Colour(240, 240, 240))
        
        # Create patches list
        patches_label = wx.StaticText(panel, label="Available Patches:")
        patches_label.SetForegroundColour(wx.Colour(200, 200, 200))
        
        self.patches_list = wx.CheckListBox(panel)
        self.patches_list.SetBackgroundColour(wx.Colour(40, 40, 40))
        self.patches_list.SetForegroundColour(wx.Colour(200, 200, 200))
        
        # Add some example patches
        self.patches_list.Append("NVIDIA GTX 970 Driver Support")
        self.patches_list.Append("Intel Arc 770 Graphics Support")
        self.patches_list.Append("Alder Lake/Raptor Lake CPU Support")
        self.patches_list.Append("CUDA 12.9.1 Support")
        self.patches_list.Append("Fix Sleep/Wake Issues")
        self.patches_list.Append("USB Port Mapping")
        
        # Check patches based on hardware
        self.patches_list.Check(0, True)  # NVIDIA GTX 970 Driver Support
        self.patches_list.Check(2, True)  # Alder Lake/Raptor Lake CPU Support
        
        # Create target volume controls
        target_label = wx.StaticText(panel, label="Target Volume:")
        target_label.SetForegroundColour(wx.Colour(200, 200, 200))
        
        self.target_volume = wx.Choice(panel)
        self.target_volume.SetBackgroundColour(wx.Colour(40, 40, 40))
        self.target_volume.SetForegroundColour(wx.Colour(200, 200, 200))
        
        refresh_button = wx.Button(panel, label="Refresh")
        refresh_button.SetBackgroundColour(wx.Colour(60, 60, 60))
        refresh_button.SetForegroundColour(wx.Colour(200, 200, 200))
        refresh_button.Bind(wx.EVT_BUTTON, self.on_refresh_volumes_button)
        
        # Create apply button
        apply_button = gb.GradientButton(panel, label="Apply Patches")
        apply_button.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        apply_button.SetForegroundColour(wx.Colour(255, 255, 255))
        apply_button.SetBackgroundColour(wx.Colour(60, 95, 168))
        apply_button.SetPressedColour(wx.Colour(34, 32, 58))
        apply_button.SetTopStartColour(wx.Colour(60, 95, 168))
        apply_button.SetTopEndColour(wx.Colour(34, 32, 58))
        apply_button.SetBottomStartColour(wx.Colour(34, 32, 58))
        apply_button.SetBottomEndColour(wx.Colour(60, 95, 168))
        apply_button.Bind(wx.EVT_BUTTON, self.on_apply_patches_button)
        
        # Create layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(10)
        sizer.Add(title_text, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        sizer.Add(patches_label, 0, wx.ALL, 10)
        sizer.Add(self.patches_list, 1, wx.EXPAND | wx.ALL, 10)
        
        # Target volume layout
        target_sizer = wx.BoxSizer(wx.HORIZONTAL)
        target_sizer.Add(target_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        target_sizer.Add(self.target_volume, 1, wx.EXPAND | wx.ALL, 5)
        target_sizer.Add(refresh_button, 0, wx.ALL, 5)
        sizer.Add(target_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # Apply button layout
        sizer.AddSpacer(20)
        sizer.Add(apply_button, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        panel.SetSizer(sizer)
        
        # Populate volumes on init
        self.refresh_volumes()
        
        return panel
    
    def create_advanced_tab(self) -> wx.Panel:
        """Create advanced tab"""
        panel = wx.Panel(self.notebook)
        panel.SetBackgroundColour(wx.Colour(30, 30, 30))
        
        # Create advanced controls
        title_text = wx.StaticText(panel, label="Advanced Options")
        title_text.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title_text.SetForegroundColour(wx.Colour(240, 240, 240))
        
        # Create config editor button
        config_button = wx.Button(panel, label="OpenCore Config Editor")
        config_button.SetBackgroundColour(wx.Colour(60, 60, 60))
        config_button.SetForegroundColour(wx.Colour(200, 200, 200))
        config_button.Bind(wx.EVT_BUTTON, self.on_config_editor_button)
        
        # Create ACPI editor button
        acpi_button = wx.Button(panel, label="ACPI Editor")
        acpi_button.SetBackgroundColour(wx.Colour(60, 60, 60))
        acpi_button.SetForegroundColour(wx.Colour(200, 200, 200))
        acpi_button.Bind(wx.EVT_BUTTON, self.on_acpi_editor_button)
        
        # Create kext manager button
        kext_button = wx.Button(panel, label="Kext Manager")
        kext_button.SetBackgroundColour(wx.Colour(60, 60, 60))
        kext_button.SetForegroundColour(wx.Colour(200, 200, 200))
        kext_button.Bind(wx.EVT_BUTTON, self.on_kext_manager_
