#!/usr/bin/env python3
"""
usb_creator.py
Skyscope macOS Patcher - USB Installer Creator

Creates bootable USB installers from macOS IPSW files with custom kexts,
configuration files, and Skyscope patcher integration for NVIDIA and Intel Arc hardware.

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
import zipfile
import plistlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, Any

try:
    import requests
    from tqdm import tqdm
except ImportError:
    print("Required packages not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "tqdm"])
    import requests
    from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'usb_creator.log'))
    ]
)
logger = logging.getLogger('USBCreator')

# Constants
DEFAULT_WORK_DIR = os.path.expanduser("~/Library/Caches/SkyscopePatcher/USBCreator")
EFI_SIZE_MB = 200  # Size of EFI partition in MB
INSTALLER_LABEL = "Skyscope_Installer"

# Hardware configurations
HARDWARE_CONFIGS = {
    "nvidia_gtx970": {
        "name": "NVIDIA GTX 970",
        "kexts": ["Lilu.kext", "WhateverGreen.kext", "NVBridgeCore.kext", "NVBridgeMetal.kext", "NVBridgeCUDA.kext"],
        "boot_args": "ngfxcompat=1 ngfxgl=1 nvda_drv_vrl=1 -v",
        "smbios": "MacPro7,1",
        "config_patches": {
            "NVRAM/Add/7C436110-AB2A-4BBB-A880-FE41995C9F82/csr-active-config": "03000000",
            "DeviceProperties/Add/PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)": {
                "device-id": "13C2",
                "vendor-id": "10DE",
                "AAPL,slot-name": "Slot-1",
                "model": "NVIDIA GeForce GTX 970"
            }
        }
    },
    "intel_arc770": {
        "name": "Intel Arc A770",
        "kexts": ["Lilu.kext", "WhateverGreen.kext", "ArcBridgeCore.kext", "ArcBridgeMetal.kext"],
        "boot_args": "iarccompat=1 iarcgl=1 -v",
        "smbios": "MacPro7,1",
        "config_patches": {
            "NVRAM/Add/7C436110-AB2A-4BBB-A880-FE41995C9F82/csr-active-config": "03000000",
            "DeviceProperties/Add/PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)": {
                "device-id": "56A0",
                "vendor-id": "8086",
                "AAPL,slot-name": "Slot-1",
                "model": "Intel Arc A770"
            }
        }
    },
    "intel_alderlake": {
        "name": "Intel Alder Lake",
        "kexts": ["Lilu.kext", "CpuTopologyRebuild.kext", "CPUFriend.kext"],
        "boot_args": "ipc_control_port_options=0 -v",
        "smbios": "MacPro7,1",
        "config_patches": {
            "Kernel/Emulate": {
                "Cpuid1Data": "55060A00000000000000000000000000",
                "Cpuid1Mask": "FFFFFFFF000000000000000000000000"
            }
        }
    },
    "intel_raptorlake": {
        "name": "Intel Raptor Lake",
        "kexts": ["Lilu.kext", "CpuTopologyRebuild.kext", "CPUFriend.kext"],
        "boot_args": "ipc_control_port_options=0 -v",
        "smbios": "MacPro7,1",
        "config_patches": {
            "Kernel/Emulate": {
                "Cpuid1Data": "B5060A00000000000000000000000000",
                "Cpuid1Mask": "FFFFFFFF000000000000000000000000"
            }
        }
    }
}

class USBCreator:
    """Class to handle creation of bootable USB installers"""
    
    def __init__(self, work_dir: str = DEFAULT_WORK_DIR):
        """
        Initialize the USB creator
        
        Args:
            work_dir: Directory to store temporary files
        """
        self.work_dir = work_dir
        self.temp_dir = os.path.join(work_dir, "temp")
        self.extract_dir = os.path.join(work_dir, "extract")
        self.kexts_dir = os.path.join(work_dir, "kexts")
        self.efi_dir = os.path.join(work_dir, "EFI")
        
        # Create directories
        for directory in [self.work_dir, self.temp_dir, self.extract_dir, self.kexts_dir, self.efi_dir]:
            os.makedirs(directory, exist_ok=True)
        
        # Check if running as root
        self.is_root = os.geteuid() == 0 if hasattr(os, 'geteuid') else False
        
        # Detect platform
        self.platform = platform.system().lower()
        if self.platform not in ['darwin', 'linux']:
            logger.warning(f"Unsupported platform: {self.platform}. Only macOS and Linux are fully supported.")
    
    def check_requirements(self) -> bool:
        """
        Check if all requirements are met
        
        Returns:
            bool: True if all requirements are met, False otherwise
        """
        # Check if running as root (required for disk operations)
        if not self.is_root:
            logger.error("This script must be run as root (sudo) to perform disk operations")
            return False
        
        # Check for required tools
        required_tools = []
        
        if self.platform == 'darwin':
            required_tools = ['diskutil', 'hdiutil', 'asr']
        elif self.platform == 'linux':
            required_tools = ['parted', 'mkfs.fat', 'mkfs.hfsplus']
        
        missing_tools = []
        for tool in required_tools:
            if not self._check_tool_exists(tool):
                missing_tools.append(tool)
        
        if missing_tools:
            logger.error(f"Missing required tools: {', '.join(missing_tools)}")
            return False
        
        return True
    
    def _check_tool_exists(self, tool: str) -> bool:
        """
        Check if a command-line tool exists
        
        Args:
            tool: Name of the tool to check
            
        Returns:
            bool: True if the tool exists, False otherwise
        """
        try:
            subprocess.run(['which', tool], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def list_disks(self) -> List[Dict[str, Any]]:
        """
        List available disks
        
        Returns:
            List[Dict]: List of dictionaries with disk information
        """
        disks = []
        
        if self.platform == 'darwin':
            # Use diskutil on macOS
            try:
                output = subprocess.check_output(['diskutil', 'list', '-plist'], universal_newlines=True)
                plist_data = plistlib.loads(output.encode('utf-8'))
                
                for disk in plist_data.get('AllDisksAndPartitions', []):
                    if disk.get('DeviceIdentifier', '').startswith('disk'):
                        # Skip internal disks
                        if self._is_internal_disk(disk.get('DeviceIdentifier')):
                            continue
                        
                        # Get disk info
                        disk_info = {
                            'identifier': disk.get('DeviceIdentifier'),
                            'size': disk.get('Size', 0),
                            'size_gb': disk.get('Size', 0) / (1024 * 1024 * 1024),
                            'name': disk.get('DeviceIdentifier'),
                            'removable': self._is_removable_disk(disk.get('DeviceIdentifier')),
                            'partitions': []
                        }
                        
                        # Add partitions
                        for partition in disk.get('Partitions', []):
                            disk_info['partitions'].append({
                                'name': partition.get('VolumeName', ''),
                                'identifier': partition.get('DeviceIdentifier'),
                                'size': partition.get('Size', 0),
                                'size_gb': partition.get('Size', 0) / (1024 * 1024 * 1024),
                                'filesystem': partition.get('Content', '')
                            })
                        
                        disks.append(disk_info)
                
            except Exception as e:
                logger.error(f"Failed to list disks: {e}")
        
        elif self.platform == 'linux':
            # Use lsblk on Linux
            try:
                output = subprocess.check_output(['lsblk', '-J', '-o', 'NAME,SIZE,MODEL,VENDOR,MOUNTPOINT,FSTYPE,TYPE,HOTPLUG'], universal_newlines=True)
                lsblk_data = json.loads(output)
                
                for device in lsblk_data.get('blockdevices', []):
                    if device.get('type') == 'disk' and device.get('hotplug') == 1:
                        disk_name = device.get('name')
                        
                        # Get disk info
                        disk_info = {
                            'identifier': f"/dev/{disk_name}",
                            'size': self._parse_size(device.get('size', '0')),
                            'size_gb': self._parse_size(device.get('size', '0')) / (1024 * 1024 * 1024),
                            'name': f"{device.get('vendor', '')} {device.get('model', '')}".strip() or disk_name,
                            'removable': True,
                            'partitions': []
                        }
                        
                        # Add partitions
                        for child in device.get('children', []):
                            if child.get('type') == 'part':
                                disk_info['partitions'].append({
                                    'name': os.path.basename(child.get('mountpoint', '')),
                                    'identifier': f"/dev/{child.get('name')}",
                                    'size': self._parse_size(child.get('size', '0')),
                                    'size_gb': self._parse_size(child.get('size', '0')) / (1024 * 1024 * 1024),
                                    'filesystem': child.get('fstype', '')
                                })
                        
                        disks.append(disk_info)
                
            except Exception as e:
                logger.error(f"Failed to list disks: {e}")
        
        return disks
    
    def _is_internal_disk(self, disk_id: str) -> bool:
        """
        Check if a disk is internal
        
        Args:
            disk_id: Disk identifier
            
        Returns:
            bool: True if the disk is internal, False otherwise
        """
        if self.platform == 'darwin':
            try:
                output = subprocess.check_output(['diskutil', 'info', '-plist', disk_id], universal_newlines=True)
                plist_data = plistlib.loads(output.encode('utf-8'))
                
                # Check if it's an internal disk
                return plist_data.get('Internal', False)
                
            except Exception:
                # If we can't determine, assume it's internal to be safe
                return True
        
        # On other platforms, we can't easily determine this
        return False
    
    def _is_removable_disk(self, disk_id: str) -> bool:
        """
        Check if a disk is removable
        
        Args:
            disk_id: Disk identifier
            
        Returns:
            bool: True if the disk is removable, False otherwise
        """
        if self.platform == 'darwin':
            try:
                output = subprocess.check_output(['diskutil', 'info', '-plist', disk_id], universal_newlines=True)
                plist_data = plistlib.loads(output.encode('utf-8'))
                
                # Check if it's removable
                return plist_data.get('Removable', False) or plist_data.get('RemovableMedia', False)
                
            except Exception:
                # If we can't determine, assume it's not removable to be safe
                return False
        
        # On other platforms, we can't easily determine this
        return True
    
    def _parse_size(self, size_str: str) -> int:
        """
        Parse size string to bytes
        
        Args:
            size_str: Size string (e.g., "1G", "500M")
            
        Returns:
            int: Size in bytes
        """
        if not size_str:
            return 0
        
        # Remove trailing 'B' if present
        if size_str.endswith('B'):
            size_str = size_str[:-1]
        
        # Convert to bytes
        multipliers = {
            '': 1,
            'K': 1024,
            'M': 1024 * 1024,
            'G': 1024 * 1024 * 1024,
            'T': 1024 * 1024 * 1024 * 1024
        }
        
        size_str = size_str.strip()
        
        if size_str[-1].upper() in multipliers:
            return int(float(size_str[:-1]) * multipliers[size_str[-1].upper()])
        else:
            return int(float(size_str))
    
    def extract_ipsw(self, ipsw_path: str) -> bool:
        """
        Extract the IPSW file
        
        Args:
            ipsw_path: Path to the IPSW file
            
        Returns:
            bool: True if extraction was successful, False otherwise
        """
        logger.info(f"Extracting IPSW file: {ipsw_path}")
        
        # Clear extract directory
        shutil.rmtree(self.extract_dir, ignore_errors=True)
        os.makedirs(self.extract_dir, exist_ok=True)
        
        try:
            # IPSW files are essentially ZIP archives
            with zipfile.ZipFile(ipsw_path, 'r') as zip_ref:
                # Extract with progress bar
                total_size = sum(info.file_size for info in zip_ref.infolist())
                extracted_size = 0
                
                with tqdm(total=total_size, unit='B', unit_scale=True, desc="Extracting") as pbar:
                    for info in zip_ref.infolist():
                        zip_ref.extract(info, self.extract_dir)
                        extracted_size += info.file_size
                        pbar.update(info.file_size)
            
            logger.info("IPSW extraction complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to extract IPSW: {e}")
            return False
    
    def prepare_efi(self, hardware_configs: List[str]) -> bool:
        """
        Prepare the EFI directory with OpenCore and kexts
        
        Args:
            hardware_configs: List of hardware configurations to support
            
        Returns:
            bool: True if preparation was successful, False otherwise
        """
        logger.info("Preparing EFI directory")
        
        # Clear EFI directory
        shutil.rmtree(self.efi_dir, ignore_errors=True)
        os.makedirs(self.efi_dir, exist_ok=True)
        
        try:
            # Create OpenCore directory structure
            oc_dir = os.path.join(self.efi_dir, "OC")
            os.makedirs(oc_dir, exist_ok=True)
            
            for subdir in ["ACPI", "Bootstrap", "Drivers", "Kexts", "Resources", "Tools"]:
                os.makedirs(os.path.join(oc_dir, subdir), exist_ok=True)
            
            # Copy OpenCore files from resources
            resources_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "resources", "OpenCore")
            
            if os.path.exists(resources_dir):
                # Copy OpenCore.efi
                shutil.copy2(
                    os.path.join(resources_dir, "OpenCore.efi"),
                    os.path.join(oc_dir, "OpenCore.efi")
                )
                
                # Copy drivers
                for driver in ["OpenRuntime.efi", "OpenCanopy.efi", "HfsPlus.efi"]:
                    src = os.path.join(resources_dir, "Drivers", driver)
                    dst = os.path.join(oc_dir, "Drivers", driver)
                    if os.path.exists(src):
                        shutil.copy2(src, dst)
                
                # Copy base config.plist
                shutil.copy2(
                    os.path.join(resources_dir, "config.plist"),
                    os.path.join(oc_dir, "config.plist")
                )
            else:
                logger.warning(f"OpenCore resources not found at {resources_dir}")
                # Create a minimal config.plist
                self._create_minimal_config(os.path.join(oc_dir, "config.plist"))
            
            # Copy kexts based on hardware configurations
            kexts_to_copy = set()
            boot_args = []
            config_patches = {}
            smbios = None
            
            for config_name in hardware_configs:
                if config_name in HARDWARE_CONFIGS:
                    config = HARDWARE_CONFIGS[config_name]
                    kexts_to_copy.update(config["kexts"])
                    boot_args.append(config["boot_args"])
                    
                    # Merge config patches
                    for key, value in config["config_patches"].items():
                        if key not in config_patches:
                            config_patches[key] = value
                        elif isinstance(value, dict) and isinstance(config_patches[key], dict):
                            # Merge dictionaries
                            config_patches[key].update(value)
                    
                    # Use the first SMBIOS we find
                    if smbios is None:
                        smbios = config["smbios"]
                
                else:
                    logger.warning(f"Unknown hardware configuration: {config_name}")
            
            # Copy kexts
            kexts_source_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "resources", "Kexts")
            
            for kext in kexts_to_copy:
                src = os.path.join(kexts_source_dir, kext)
                dst = os.path.join(oc_dir, "Kexts", kext)
                
                if os.path.exists(src):
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                else:
                    logger.warning(f"Kext not found: {src}")
            
            # Update config.plist with hardware-specific settings
            config_path = os.path.join(oc_dir, "config.plist")
            self._update_config_plist(
                config_path,
                " ".join(boot_args),
                smbios,
                config_patches
            )
            
            # Create boot.efi symlink in EFI/BOOT
            boot_dir = os.path.join(self.efi_dir, "BOOT")
            os.makedirs(boot_dir, exist_ok=True)
            
            # Copy OpenCore as BOOTx64.efi
            shutil.copy2(
                os.path.join(oc_dir, "OpenCore.efi"),
                os.path.join(boot_dir, "BOOTx64.efi")
            )
            
            logger.info("EFI directory prepared successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to prepare EFI: {e}")
            return False
    
    def _create_minimal_config(self, config_path: str) -> None:
        """
        Create a minimal config.plist
        
        Args:
            config_path: Path to save the config.plist
        """
        minimal_config = {
            "ACPI": {
                "Add": [],
                "Delete": [],
                "Patch": []
            },
            "Booter": {
                "MmioWhitelist": [],
                "Quirks": {
                    "AvoidRuntimeDefrag": True,
                    "EnableWriteUnprotector": True,
                    "SetupVirtualMap": True
                }
            },
            "DeviceProperties": {
                "Add": {},
                "Delete": {}
            },
            "Kernel": {
                "Add": [],
                "Block": [],
                "Emulate": {},
                "Patch": [],
                "Quirks": {
                    "AppleCpuPmCfgLock": True,
                    "DisableIOMapper": True,
                    "LapicKernelPanic": False,
                    "PanicNoKextDump": True,
                    "PowerTimeoutKernelPanic": True,
                    "XhciPortLimit": True
                }
            },
            "Misc": {
                "Boot": {
                    "ConsoleAttributes": 0,
                    "HibernateMode": "None",
                    "HideAuxiliary": False,
                    "PickerAttributes": 1,
                    "PickerMode": "External",
                    "PollAppleHotKeys": True,
                    "ShowPicker": True,
                    "TakeoffDelay": 0,
                    "Timeout": 5
                },
                "Debug": {
                    "AppleDebug": True,
                    "DisableWatchDog": True,
                    "DisplayLevel": 2147483650,
                    "Target": 67
                },
                "Security": {
                    "AllowNvramReset": True,
                    "AllowSetDefault": True,
                    "ExposeSensitiveData": 6,
                    "ScanPolicy": 0,
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
                        "boot-args": "-v keepsyms=1",
                        "csr-active-config": "00000000",
                        "prev-lang:kbd": "en-US:0"
                    }
                },
                "Delete": {
                    "4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14": [],
                    "7C436110-AB2A-4BBB-A880-FE41995C9F82": []
                },
                "LegacyEnable": False,
                "LegacyOverwrite": False,
                "WriteFlash": True
            },
            "PlatformInfo": {
                "Automatic": True,
                "Generic": {
                    "MLB": "",
                    "ROM": "",
                    "SpoofVendor": True,
                    "SystemProductName": "MacPro7,1",
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
                    "HideVerbose": True,
                    "JumpstartHotPlug": False,
                    "MinDate": 0,
                    "MinVersion": 0
                },
                "Audio": {
                    "AudioCodec": 0,
                    "AudioDevice": "",
                    "AudioOut": 0,
                    "AudioSupport": False,
                    "MinimumVolume": 20,
                    "PlayChime": False,
                    "VolumeAmplifier": 0
                },
                "ConnectDrivers": True,
                "Drivers": [
                    "OpenRuntime.efi",
                    "OpenCanopy.efi",
                    "HfsPlus.efi"
                ],
                "Input": {
                    "KeyFiltering": False,
                    "KeyForgetThreshold": 5,
                    "KeyMergeThreshold": 2,
                    "KeySupport": True,
                    "KeySupportMode": "Auto",
                    "KeySwap": False,
                    "PointerSupport": False,
                    "PointerSupportMode": "",
                    "TimerResolution": 50000
                },
                "Output": {
                    "ClearScreenOnModeSwitch": False,
                    "ConsoleMode": "",
                    "DirectGopRendering": False,
                    "IgnoreTextInGraphics": False,
                    "ProvideConsoleGop": True,
                    "ReconnectOnResChange": False,
                    "ReplaceTabWithSpace": False,
                    "Resolution": "Max",
                    "SanitiseClearScreen": False,
                    "TextRenderer": "BuiltinGraphics"
                },
                "ProtocolOverrides": {
                    "AppleAudio": False,
                    "AppleBootPolicy": False,
                    "AppleDebugLog": False,
                    "AppleEvent": False,
                    "AppleFramebufferInfo": False,
                    "AppleImageConversion": False,
                    "AppleKeyMap": False,
                    "AppleRtcRam": False,
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
                    "ExitBootServicesDelay": 0,
                    "IgnoreInvalidFlexRatio": False,
                    "ReleaseUsbOwnership": True,
                    "RequestBootVarRouting": True,
                    "TscSyncTimeout": 0,
                    "UnblockFsConnect": False
                }
            }
        }
        
        with open(config_path, 'wb') as f:
            plistlib.dump(minimal_config, f)
    
    def _update_config_plist(self, config_path: str, boot_args: str, smbios: str, patches: Dict[str, Any]) -> None:
        """
        Update config.plist with hardware-specific settings
        
        Args:
            config_path: Path to the config.plist
            boot_args: Boot arguments to set
            smbios: SMBIOS to use
            patches: Dictionary of patches to apply
        """
        try:
            # Load config.plist
            with open(config_path, 'rb') as f:
                config = plistlib.load(f)
            
            # Update boot args
            if 'NVRAM' in config and 'Add' in config['NVRAM'] and '7C436110-AB2A-4BBB-A880-FE41995C9F82' in config['NVRAM']['Add']:
                config['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']['boot-args'] = boot_args
            
            # Update SMBIOS
            if 'PlatformInfo' in config and 'Generic' in config['PlatformInfo']:
                config['PlatformInfo']['Generic']['SystemProductName'] = smbios
            
            # Apply patches
            for path, value in patches.items():
                # Split path into components
                components = path.split('/')
                
                # Navigate to the target location
                current = config
                for i, component in enumerate(components):
                    if i == len(components) - 1:
                        # Last component, set the value
                        current[component] = value
                    else:
                        # Create intermediate dictionaries if they don't exist
                        if component not in current:
                            current[component] = {}
                        current = current[component]
            
            # Update kexts list
            if 'Kernel' in config and 'Add' in config['Kernel']:
                kexts_dir = os.path.join(os.path.dirname(config_path), "Kexts")
                kexts_entries = []
                
                for kext_name in os.listdir(kexts_dir):
                    if kext_name.endswith('.kext'):
                        kext_path = os.path.join(kexts_dir, kext_name)
                        info_plist_path = os.path.join(kext_path, "Contents", "Info.plist")
                        
                        if os.path.exists(info_plist_path):
                            try:
                                with open(info_plist_path, 'rb') as f:
                                    info_plist = plistlib.load(f)
                                
                                bundle_id = info_plist.get('CFBundleIdentifier', f"com.skyscope.{kext_name}")
                                version = info_plist.get('CFBundleVersion', '1.0.0')
                                
                                kexts_entries.append({
                                    'BundlePath': kext_name,
                                    'Comment': f"{kext_name}",
                                    'Enabled': True,
                                    'ExecutablePath': self._find_executable_path(kext_path),
                                    'MaxKernel': '',
                                    'MinKernel': '',
                                    'PlistPath': 'Contents/Info.plist'
                                })
                            except Exception as e:
                                logger.warning(f"Failed to process kext {kext_name}: {e}")
                
                config['Kernel']['Add'] = kexts_entries
            
            # Save updated config
            with open(config_path, 'wb') as f:
                plistlib.dump(config, f)
            
            logger.info(f"Updated config.plist at {config_path}")
            
        except Exception as e:
            logger.error(f"Failed to update config.plist: {e}")
    
    def _find_executable_path(self, kext_path: str) -> str:
        """
        Find the executable path for a kext
        
        Args:
            kext_path: Path to the kext
            
        Returns:
            str: Relative path to the executable, or empty string if not found
        """
        # Check common locations
        macos_dir = os.path.join(kext_path, "Contents", "MacOS")
        if os.path.exists(macos_dir):
            # Get the first executable in the MacOS directory
            executables = os.listdir(macos_dir)
            if executables:
                return f"Contents/MacOS/{executables[0]}"
        
        return ""
    
    def prepare_usb(self, disk_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Prepare the USB disk (format and partition)
        
        Args:
            disk_id: Disk identifier
            
        Returns:
            Tuple[bool, Optional[str], Optional[str]]: (Success, EFI partition path, Installer partition path)
        """
        logger.info(f"Preparing USB disk: {disk_id}")
        
        if self.platform == 'darwin':
            return self._prepare_usb_macos(disk_id)
        elif self.platform == 'linux':
            return self._prepare_usb_linux(disk_id)
        else:
            logger.error(f"Unsupported platform: {self.platform}")
            return False, None, None
    
    def _prepare_usb_macos(self, disk_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Prepare USB disk on macOS
        
        Args:
            disk_id: Disk identifier
            
        Returns:
            Tuple[bool, Optional[str], Optional[str]]: (Success, EFI partition path, Installer partition path)
        """
        try:
            # Unmount all partitions
            subprocess.run(['diskutil', 'unmountDisk', disk_id], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Partition the disk (GUID partition scheme, EFI + APFS)
            logger.info("Partitioning disk...")
            subprocess.run([
                'diskutil', 'partitionDisk', disk_id, '2', 'GPT',
                'EFI', 'FAT32', f'{EFI_SIZE_MB}M',
                'Install', 'APFS', 'R'
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Get partition identifiers
            efi_id = f"{disk_id}s1"
            installer_id = f"{disk_id}s2"
            
            # Mount EFI partition
            subprocess.run(['diskutil', 'mount', efi_id], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Get mount points
            efi_mount = None
            installer_mount = None
            
            output = subprocess.check_output(['diskutil', 'info', '-plist', efi_id], universal_newlines=True)
            plist_data = plistlib.loads(output.encode('utf-8'))
            efi_mount = plist_data.get('MountPoint')
            
            output = subprocess.check_output(['diskutil', 'info', '-plist', installer_id], universal_newlines=True)
            plist_data = plistlib.loads(output.encode('utf-8'))
            installer_mount = plist_data.get('MountPoint')
            
            logger.info(f"USB prepared: EFI at {efi_mount}, Installer at {installer_mount}")
            return True, efi_mount, installer_mount
            
        except Exception as e:
            logger.error(f"Failed to prepare USB: {e}")
            return False, None, None
    
    def _prepare_usb_linux(self, disk_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Prepare USB disk on Linux
        
        Args:
            disk_id: Disk identifier
            
        Returns:
            Tuple[bool, Optional[str], Optional[str]]: (Success, EFI partition path, Installer partition path)
        """
        try:
            # Unmount all partitions
            subprocess.run(['umount', f"{disk_id}*"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Create new partition table (GPT)
            subprocess.run(['parted', '-s', disk_id, 'mklabel', 'gpt'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Create EFI partition
            subprocess.run([
                'parted', '-s', disk_id, 
                'mkpart', 'primary', 'fat32', '1MiB', f'{EFI_SIZE_MB+1}MiB',
                'set', '1', 'boot', 'on',
                'set', '1', 'esp', 'on'
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Create installer partition
            subprocess.run([
                'parted', '-s', disk_id,
                'mkpart', 'primary', 'hfs+', f'{EFI_SIZE_MB+1}MiB', '100%'
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Format EFI partition
            efi_part = f"{disk_id}1"
            subprocess.run(['mkfs.fat', '-F', '32', '-n', 'EFI', efi_part], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Format installer partition
            installer_part = f"{disk_id}2"
            subprocess.run(['mkfs.hfsplus', '-v', INSTALLER_LABEL, installer_part], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Create mount points
            efi_mount = os.path.join(self.temp_dir, "efi_mount")
            installer_mount = os.path.join(self.temp_dir, "installer_mount")
            
            os.makedirs(efi_mount, exist_ok=True)
            os.makedirs(installer_mount, exist_ok=True)
            
            # Mount partitions
            subprocess.run(['mount', efi_part, efi_mount], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(['mount', installer_part, installer_mount], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            logger.info(f"USB prepared: EFI at {efi_mount}, Installer at {installer_mount}")
            return True, efi_mount, installer_mount
            
        except Exception as e:
            logger.error(f"Failed to prepare USB: {e}")
            return False, None, None
    
    def copy_installer_files(self, installer_mount: str) -> bool:
        """
        Copy installer files to the USB
        
        Args:
            installer_mount: Mount point of the installer partition
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Copying installer files to {installer_mount}")
        
        try:
            # Find SharedSupport.dmg in the extracted IPSW
            shared_support_path = None
            
            for root, _, files in os.walk(self.extract_dir):
                for file in files:
                    if file == 'SharedSupport.dmg':
                        shared_support_path = os.path.join(root, file)
                        break
                if shared_support_path:
                    break
            
            if not shared_support_path:
                logger.error("SharedSupport.dmg not found in extracted IPSW")
                return False
            
            # Mount SharedSupport.dmg
            shared_mount = os.path.join(self.temp_dir, "shared_mount")
            os.makedirs(shared_mount, exist_ok=True)
            
            if self.platform == 'darwin':
                subprocess.run(['hdiutil', 'attach', shared_support_path, '-mountpoint', shared_mount, '-nobrowse'], 
                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            elif self.platform == 'linux':
                # Create a loopback device
                loop_dev = subprocess.check_output(['losetup', '-f'], universal_newlines=True).strip()
                subprocess.run(['losetup', loop_dev, shared_support_path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(['mount', loop_dev, shared_mount], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Find InstallAssistant.pkg
            install_assistant_path = None
            
            for root, _, files in os.walk(shared_mount):
                for file in files:
                    if file == 'InstallAssistant.pkg':
                        install_assistant_path = os.path.join(root, file)
                        break
                if install_assistant_path:
                    break
            
            if not install_assistant_path:
                logger.error("InstallAssistant.pkg not found in SharedSupport.dmg")
                return False
            
            # Extract InstallAssistant.pkg
            pkg_extract_dir = os.path.join(self.temp_dir, "pkg_extract")
            os.makedirs(pkg_extract_dir, exist_ok=True)
            
            if self.platform == 'darwin':
                subprocess.run(['pkgutil', '--expand', install_assistant_path, pkg_extract_dir], 
                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            elif self.platform == 'linux':
                # Extract using xar
                subprocess.run(['xar', '-xf', install_assistant_path, '-C', pkg_extract_dir], 
                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Find the largest payload
            payload_path = None
            max_size = 0
            
            for root, _, files in os.walk(pkg_extract_dir):
                for file in files:
                    if file.startswith('Payload'):
                        file_path = os.path.join(root, file)
                        file_size = os.path.getsize(file_path)
                        
                        if file_size > max_size:
                            max_size = file_size
                            payload_path = file_path
            
            if not payload_path:
                logger.error("Payload not found in InstallAssistant.pkg")
                return False
            
            # Extract payload
            payload_extract_dir = os.path.join(self.temp_dir, "payload_extract")
            os.makedirs(payload_extract_dir, exist_ok=True)
            
            if self.platform == 'darwin':
                # Extract using cpio
                cpio_process = subprocess.Popen(['cat', payload_path], stdout=subprocess.PIPE)
                subprocess.run(['gunzip', '-dc'], stdin=cpio_process.stdout, stdout=subprocess.PIPE, 
                               input=subprocess.Popen(['cpio', '-i', '-D', payload_extract_dir], 
                                                     stdin=subprocess.PIPE).stdin)
            elif self.platform == 'linux':
                # Extract using cpio
                subprocess.run(f"cat {payload_path} | gunzip -dc | (cd {payload_extract_dir} && cpio -i)", 
                               shell=True, check=True)
            
            # Find Install macOS app
            app_path = None
            
            for root, dirs, _ in os.walk(payload_extract_dir):
                for dir_name in dirs:
                    if dir_name.startswith('Install macOS') and dir_name.endswith('.app'):
                        app_path = os.path.join(root, dir_name)
                        break
                if app_path:
                    break
            
            if not app_path:
                logger.error("Install macOS app not found in payload")
                return False
            
            # Copy Install macOS app to USB
            usb_app_path = os.path.join(installer_mount, os.path.basename(app_path))
            
            logger.info(f"Copying {app_path} to {usb_app_path}")
            shutil.copytree(app_path, usb_app_path)
            
            # Copy Skyscope patcher to USB
            skyscope_dir = os.path.join(installer_mount, "Skyscope")
            os.makedirs(skyscope_dir, exist_ok=True)
            
            # Copy patcher files
            patcher_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
            
            for item in ["skyscope_enhanced.py", "build_complete_skyscope.sh", "advanced_config.json"]:
                src = os.path.join(patcher_dir, item)
                if os.path.exists(src):
                    dst = os.path.join(skyscope_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
            
            # Copy source directories
            for src_dir in ["src", "resources"]:
                src = os.path.join(patcher_dir, src_dir)
                if os.path.exists(src):
                    dst = os.path.join(skyscope_dir, src_dir)
                    shutil.copytree(src, dst)
            
            # Create README file
            with open(os.path.join(skyscope_dir, "README.txt"), 'w') as f:
                f.write("Skyscope macOS Patcher\n")
                f.write("======================\n\n")
                f.write("This USB installer includes the Skyscope patcher for enabling NVIDIA and Intel Arc support in macOS.\n\n")
                f.write("To use the patcher:\n")
                f.write("1. Boot from this USB drive using OpenCore\n")
                f.write("2. Install macOS\n")
                f.write("3. After installation, boot into the new macOS installation\n")
                f.write("4. Open Terminal and run:\n")
                f.write("   cd /Volumes/Skyscope_Installer/Skyscope\n")
                f.write("   sudo ./build_complete_skyscope.sh\n\n")
                f.write("This will install the necessary kexts and configurations for your hardware.\n")
            
            # Clean up
            if self.platform == 'darwin':
                subprocess.run(['hdiutil', 'detach', shared_mount], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            elif self.platform == 'linux':
                subprocess.run(['umount', shared_mount], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(['losetup', '-d', loop_dev], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            logger.info("Installer files copied successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy installer files: {e}")
            return False
    
    def copy_efi_files(self, efi_mount: str) -> bool:
        """
        Copy EFI files to the USB
        
        Args:
            efi_mount: Mount point of the EFI partition
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Copying EFI files to {efi_mount}")
        
        try:
            # Copy EFI directory
            for item in os.listdir(self.efi_dir):
                src = os.path.join(self.efi_dir, item)
                dst = os.path.join(efi_mount, item)
                
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            
            logger.info("EFI files copied successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy EFI files: {e}")
            return False
    
    def finalize_usb(self, efi_mount: str, installer_mount: str) -> bool:
        """
        Finalize the USB installer
        
        Args:
            efi_mount: Mount point of the EFI partition
            installer_mount: Mount point of the installer partition
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Finalizing USB installer")
        
        try:
            # Create a file with hardware configurations
            with open(os.path.join(installer_mount, "Skyscope", "hardware_config.txt"), 'w') as f:
                f.write("Skyscope macOS Patcher - Hardware Configurations\n")
                f.write("===========================================\n\n")
                
                for config_name, config in HARDWARE_CONFIGS.items():
                    f.write(f"{config['name']}:\n")
                    f.write(f"  Boot Args: {config['boot_args']}\n")
                    f.write(f"  SMBIOS: {config['smbios']}\n")
                    f.write(f"  Kexts: {', '.join(config['kexts'])}\n\n")
            
            # Create a timestamp file
            with open(os.path.join(installer_mount, "Skyscope", "created.txt"), 'w') as f:
                f.write(f"USB installer created on: {datetime.now().isoformat()}\n")
                f.write(f"Created by: Skyscope macOS Patcher USB Creator v1.0.0\n")
            
            # Sync filesystems
            if self.platform == 'darwin':
                subprocess.run(['sync'], check=True)
            elif self.platform == 'linux':
                subprocess.run(['sync'], check=True)
            
            logger.info("USB installer finalized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to finalize USB installer: {e}")
            return False
    
    def create_usb_installer(self, ipsw_path: str, disk_id: str, hardware_configs: List[str]) -> bool:
        """
        Create a bootable USB installer
        
        Args:
            ipsw_path: Path to the IPSW file
            disk_id: Disk identifier
            hardware_configs: List of hardware configurations to support
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Creating USB installer: IPSW={ipsw_path}, Disk={disk_id}")
        
        # Check requirements
        if not self.check_requirements():
            return False
        
        # Extract IPSW
        if not self.extract_ipsw(ipsw_path):
            return False
        
        # Prepare EFI
        if not self.prepare_efi(hardware_configs):
            return False
        
        # Prepare USB
        success, efi_mount, installer_mount = self.prepare_usb(disk_id)
        if not success or not efi_mount or not installer_mount:
            return False
        
        # Copy EFI files
        if not self.copy_efi_files(efi_mount):
            return False
        
        # Copy installer files
        if not self.copy_installer_files(installer_mount):
            return False
        
        # Finalize USB
        if not self.finalize_usb(efi_mount, installer_mount):
            return False
        
        logger.info("USB installer created successfully")
        return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Create bootable macOS USB installer with Skyscope patcher')
    
    parser.add_argument('--ipsw', required=True, help='Path to macOS IPSW file')
    parser.add_argument('--disk', required=True, help='Disk identifier for USB drive')
    parser.add_argument('--work-dir', default=DEFAULT_WORK_DIR, help='Working directory')
    parser.add_argument('--hardware', nargs='+', default=['nvidia_gtx970', 'intel_arc770'], 
                        choices=HARDWARE_CONFIGS.keys(), help='Hardware configurations to support')
    parser.add_argument('--list-disks', action='store_true', help='List available disks')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Create USB creator
    creator = USBCreator(work_dir=args.work_dir)
    
    # Handle commands
    if args.list_disks:
        disks = creator.list_disks()
        
        print("Available disks:")
        for disk in disks:
            print(f"  {disk['identifier']}: {disk['name']} ({disk['size_gb']:.2f} GB)")
            
            for partition in disk['partitions']:
                print(f"    - {partition['identifier']}: {partition['name']} ({partition['size_gb']:.2f} GB, {partition['filesystem']})")
        
        return 0
    
    # Check if running as root
    if not creator.is_root:
        print("Error: This script must be run as root (sudo) to perform disk operations")
        return 1
    
    # Create USB installer
    success = creator.create_usb_installer(args.ipsw, args.disk, args.hardware)
    
    if success:
        print("\nUSB installer created successfully!")
        print("You can now boot from this USB drive to install macOS with Skyscope patcher.")
        return 0
    else:
        print("\nFailed to create USB installer. Check the logs for details.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
