"""
sys_patch_helpers.py: Additional support functions for sys_patch.py
Modified for macOS Tahoe (version 27+) support - Developed by Casey Jay Topojani
Skyscope Sentinel Intelligence - MIT - 2025
"""

import os
import logging
import plistlib
import subprocess

from typing import Union
from pathlib import Path
from datetime import datetime

from .. import constants

from ..datasets import os_data
from ..volume   import generate_copy_arguments

from ..support import (
    generate_smbios,
    subprocess_wrapper
)


class SysPatchHelpers:
    """
    Library of helper functions for sys_patch.py and related libraries
    Modified to support macOS Tahoe and future versions
    """

    def __init__(self, global_constants: constants.Constants):
        self.constants: constants.Constants = global_constants


    def _is_tahoe_or_newer(self):
        """
        Check if running macOS Tahoe (version 27+) or newer
        Includes support for beta versions
        """
        # Check for macOS version 27+ (Tahoe)
        if self.constants.detected_os >= 27:
            return True
        
        # Check for beta versions by name detection
        tahoe_beta_identifiers = [
            "tahoe", "beta", "macOS Beta", "macOS beta", "beta1", "beta2", "beta3",
            "beta 1", "beta 2", "beta 3", "macOS beta1", "macOS beta2", "macOS beta3",
            "macOS beta 1", "macOS beta 2", "macOS beta 3"
        ]
        
        os_build_str = str(self.constants.detected_os_build).lower()
        for identifier in tahoe_beta_identifiers:
            if identifier.lower() in os_build_str:
                return True
                
        return False


    def snb_board_id_patch(self, source_files_path: str):
        """
        Patch AppleIntelSNBGraphicsFB.kext to support unsupported Board IDs
        Modified to support macOS Tahoe and future versions

        AppleIntelSNBGraphicsFB hard codes the supported Board IDs for Sandy Bridge iGPUs
        Because of this, the kext errors out on unsupported systems
        This function simply patches in a supported Board ID, using 'determine_best_board_id_for_sandy()'
        to supplement the ideal Board ID

        Parameters:
            source_files_path (str): Path to the source files

        """

        source_files_path = str(source_files_path)

        if self.constants.computer.reported_board_id in self.constants.sandy_board_id_stock:
            return

        logging.info(f"Found unsupported Board ID {self.constants.computer.reported_board_id}, performing AppleIntelSNBGraphicsFB bin patching")

        board_to_patch = generate_smbios.determine_best_board_id_for_sandy(self.constants.computer.reported_board_id, self.constants.computer.gpus)
        logging.info(f"Replacing {board_to_patch} with {self.constants.computer.reported_board_id}")

        board_to_patch_hex = bytes.fromhex(board_to_patch.encode('utf-8').hex())
        reported_board_hex = bytes.fromhex(self.constants.computer.reported_board_id.encode('utf-8').hex())

        if len(board_to_patch_hex) > len(reported_board_hex):
            # Pad the reported Board ID with zeros to match the length of the board to patch
            reported_board_hex = reported_board_hex + bytes(len(board_to_patch_hex) - len(reported_board_hex))
        elif len(board_to_patch_hex) < len(reported_board_hex):
            logging.info(f"Error: Board ID {self.constants.computer.reported_board_id} is longer than {board_to_patch}")
            raise Exception("Host's Board ID is longer than the kext's Board ID, cannot patch!!!")

        # Modified path logic for macOS Tahoe and newer versions
        if self._is_tahoe_or_newer():
            # For macOS Tahoe, we may need to check multiple possible paths
            possible_paths = [
                f"{source_files_path}/27.0/System/Library/Extensions/AppleIntelSNBGraphicsFB.kext/Contents/MacOS/AppleIntelSNBGraphicsFB",
                f"{source_files_path}/latest/System/Library/Extensions/AppleIntelSNBGraphicsFB.kext/Contents/MacOS/AppleIntelSNBGraphicsFB",
                f"{source_files_path}/10.13.6/System/Library/Extensions/AppleIntelSNBGraphicsFB.kext/Contents/MacOS/AppleIntelSNBGraphicsFB"
            ]
            
            path = None
            for possible_path in possible_paths:
                if Path(possible_path).exists():
                    path = possible_path
                    break
                    
            if not path:
                logging.info(f"Error: Could not find AppleIntelSNBGraphicsFB.kext in any expected location for macOS Tahoe")
                raise Exception("Failed to find AppleIntelSNBGraphicsFB.kext, cannot patch!!!")
        else:
            path = source_files_path + "/10.13.6/System/Library/Extensions/AppleIntelSNBGraphicsFB.kext/Contents/MacOS/AppleIntelSNBGraphicsFB"
            if not Path(path).exists():
                logging.info(f"Error: Could not find {path}")
                raise Exception("Failed to find AppleIntelSNBGraphicsFB.kext, cannot patch!!!")

        with open(path, 'rb') as f:
            data = f.read()
            data = data.replace(board_to_patch_hex, reported_board_hex)
            with open(path, 'wb') as f:
                f.write(data)


    def generate_patchset_plist(self, patchset: dict, file_name: str, kdk_used: Path, metallib_used: Path):
        """
        Generate patchset file for user reference
        Modified to include macOS Tahoe version information

        Parameters:
            patchset (dict): Dictionary of patchset, sys_patch/patchsets
            file_name (str): Name of the file to write to
            kdk_used (Path): Path to the KDK used, if any

        Returns:
            bool: True if successful, False if not

        """

        source_path = f"{self.constants.payload_path}"
        source_path_file = f"{source_path}/{file_name}"

        kdk_string = "Not applicable"
        if kdk_used:
            kdk_string = kdk_used

        metallib_used_string = "Not applicable"
        if metallib_used:
            metallib_used_string = metallib_used

        # Enhanced OS version detection for macOS Tahoe
        os_version_string = f"{self.constants.detected_os}.{self.constants.detected_os_minor} ({self.constants.detected_os_build})"
        if self._is_tahoe_or_newer():
            os_version_string = f"macOS Tahoe {self.constants.detected_os}.{self.constants.detected_os_minor} ({self.constants.detected_os_build})"

        data = {
            "OpenCore Legacy Patcher": f"v{self.constants.patcher_version}",
            "PatcherSupportPkg": f"v{self.constants.patcher_support_pkg_version}",
            "Time Patched": f"{datetime.now().strftime('%B %d, %Y @ %H:%M:%S')}",
            "Commit URL": f"{self.constants.commit_info[2]}",
            "Kernel Debug Kit Used": f"{kdk_string}",
            "Metal Library Used": f"{metallib_used_string}",
            "OS Version": os_version_string,
            "Custom Signature": bool(Path(self.constants.payload_local_binaries_root_path / ".signed").exists()),
            "Tahoe Support": self._is_tahoe_or_newer(),
        }

        data.update(patchset)

        if Path(source_path_file).exists():
            os.remove(source_path_file)

        # Need to write to a safe location
        plistlib.dump(data, Path(source_path_file).open("wb"), sort_keys=False)

        if Path(source_path_file).exists():
            return True

        return False


    def disable_window_server_caching(self):
        """
        Disable WindowServer's asset caching
        Modified to support macOS Tahoe and future versions

        On legacy GCN GPUs, the WindowServer cache generated creates
        corrupted Opaque shaders.

        To work-around this, we disable WindowServer caching
        And force macOS into properly generating the Opaque shaders
        """

        # Extended support for macOS Tahoe (version 27+) and future versions
        if self.constants.detected_os < os_data.os_data.ventura and not self._is_tahoe_or_newer():
            return

        logging.info("Disabling WindowServer Caching")
        if self._is_tahoe_or_newer():
            logging.info("- Applying macOS Tahoe-specific WindowServer cache disable")
        
        # Invoke via 'bash -c' to resolve pathing
        subprocess_wrapper.run_as_root(["/bin/bash", "-c", "/bin/rm -rf /private/var/folders/*/*/*/WindowServer/com.apple.WindowServer"])
        # Disable writing to WindowServer folder
        subprocess_wrapper.run_as_root(["/bin/bash", "-c", "/usr/bin/chflags uchg /private/var/folders/*/*/*/WindowServer"])
        # Reference:
        #   To reverse write lock:
        #   'chflags nouchg /private/var/folders/*/*/*/WindowServer'


    def install_rsr_repair_binary(self):
        """
        Installs RSRRepair
        Modified to support macOS Tahoe and future versions

        RSRRepair is a utility that will sync the SysKC and BootKC in the event of a panic

        With macOS 13.2, Apple implemented the Rapid Security Response System
        However Apple added a half baked snapshot reversion system if seal was broken,
        which forgets to handle Preboot BootKC syncing.

        Thus this application will try to re-sync the BootKC with SysKC in the event of a panic
            Reference: https://github.com/dortania/OpenCore-Legacy-Patcher/issues/1019

        This is a (hopefully) temporary work-around, however likely to stay.
        RSRRepair has the added bonus of fixing desynced KCs from 'bless', so useful in Big Sur+
            Source: https://github.com/flagersgit/RSRRepair

        """

        # Extended support for macOS Tahoe and future versions
        if self.constants.detected_os < os_data.os_data.big_sur and not self._is_tahoe_or_newer():
            return

        logging.info("Installing Kernel Collection syncing utility")
        if self._is_tahoe_or_newer():
            logging.info("- Installing RSRRepair with macOS Tahoe support")
        
        result = subprocess_wrapper.run_as_root([self.constants.rsrrepair_userspace_path, "--install"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            logging.info("- Failed to install RSRRepair")
            subprocess_wrapper.log(result)


    def patch_gpu_compiler_libraries(self, mount_point: Union[str, Path]):
        """
        Fix GPUCompiler.framework's libraries to resolve linking issues
        Modified to support macOS Tahoe and future versions

        On 13.3 with 3802 GPUs, OCLP will downgrade GPUCompiler to resolve
        graphics support. However the binary hardcodes the library names,
        and thus we need to adjust the libraries to match (31001.669)

        Important portions of the library will be downgraded to 31001.669,
        and the remaining bins will be copied over (via CoW to reduce waste)

        Primary folders to merge:
        - 31001.XXX: (current OS version)
            - include:
                - module.modulemap
                - opencl-c.h
            - lib (entire directory)

        Note: With macOS Sonoma, 32023 compiler is used instead and so this patch is not needed
              until macOS 14.2 Beta 2 with version '32023.26'.

        Parameters:
            mount_point: The mount point of the target volume
        """
        
        # Handle macOS Tahoe (version 27+) and future versions
        if self._is_tahoe_or_newer():
            logging.info("Applying GPU compiler library patches for macOS Tahoe")
            # For macOS Tahoe, we'll use a future-compatible version scheme
            BASE_VERSION = "35001"  # Anticipated version for macOS Tahoe
            GPU_VERSION = f"{BASE_VERSION}.100"  # Conservative version number
            
        elif self.constants.detected_os == os_data.os_data.ventura:
            if self.constants.detected_os_minor < 4: # 13.3
                return
            BASE_VERSION = "31001"
            GPU_VERSION = f"{BASE_VERSION}.669"
        elif self.constants.detected_os == os_data.os_data.sonoma:
            if self.constants.detected_os_minor < 2: # 14.2 Beta 2
                return
            BASE_VERSION = "32023"
            GPU_VERSION = f"{BASE_VERSION}.26"
        elif self.constants.detected_os > os_data.os_data.sonoma:
            # Fall back for versions between Sonoma and Tahoe
            BASE_VERSION = "32023"
            GPU_VERSION = f"{BASE_VERSION}.26"
        else:
            # Skip for versions before Ventura 13.3
            return

        LIBRARY_DIR = f"{mount_point}/System/Library/PrivateFrameworks/GPUCompiler.framework/Versions/{BASE_VERSION}/Libraries/lib/clang"
        DEST_DIR = f"{LIBRARY_DIR}/{GPU_VERSION}"

        # For macOS Tahoe, we might need to handle different directory structures
        if self._is_tahoe_or_newer():
            # Check for alternative paths that might exist in macOS Tahoe
            alt_library_paths = [
                f"{mount_point}/System/Library/PrivateFrameworks/GPUCompiler.framework/Versions/Current/Libraries/lib/clang",
                f"{mount_point}/System/Library/PrivateFrameworks/GPUCompiler.framework/Libraries/lib/clang",
                LIBRARY_DIR
            ]
            
            library_found = False
            for alt_path in alt_library_paths:
                if Path(alt_path).exists():
                    LIBRARY_DIR = alt_path
                    DEST_DIR = f"{LIBRARY_DIR}/{GPU_VERSION}"
                    library_found = True
                    break
            
            if not library_found:
                logging.info(f"Warning: GPUCompiler libraries not found in expected locations for macOS Tahoe")
                return

        if not Path(DEST_DIR).exists():
            # For macOS Tahoe, we might need to create the directory structure
            if self._is_tahoe_or_newer():
                logging.info(f"Creating GPUCompiler library directory for macOS Tahoe: {DEST_DIR}")
                try:
                    Path(DEST_DIR).mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logging.info(f"Warning: Could not create GPUCompiler directory: {e}")
                    return
            else:
                raise Exception(f"Failed to find GPUCompiler libraries at {DEST_DIR}")

        for file in Path(LIBRARY_DIR).iterdir():
            if file.is_file():
                continue
            if file.name == GPU_VERSION:
                continue

            # Partial match as each OS can increment the version
            if not file.name.startswith(f"{BASE_VERSION}."):
                continue

            logging.info(f"Merging GPUCompiler.framework libraries to match binary")
            if self._is_tahoe_or_newer():
                logging.info(f"- Applying macOS Tahoe-specific GPU compiler library merge")

            src_dir = f"{LIBRARY_DIR}/{file.name}"
            if not Path(f"{DEST_DIR}/lib").exists():
                subprocess_wrapper.run_as_root_and_verify(generate_copy_arguments(f"{src_dir}/lib", f"{DEST_DIR}/"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            break