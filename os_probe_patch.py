#!/usr/bin/env python3
"""
os_probe_patch.py: Patch for OpenCore Legacy Patcher to support macOS beta versions
"""

import os
import re
import sys
import logging

def patch_os_probe_file(file_path):
    """
    Patch the os_probe.py file to add support for macOS beta versions 26.0-26.3
    
    Parameters:
        file_path (str): Path to the os_probe.py file
    
    Returns:
        bool: True if patching was successful, False otherwise
    """
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return False
    
    # Read the original file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Create backup
    with open(f"{file_path}.bak", 'w') as f:
        f.write(content)
    
    # Find the detect_os_version method
    detect_os_version_pattern = r'def detect_os_version\(self\)(.*?)return result\.stdout\.decode\(\)\.strip\(\)'
    match = re.search(detect_os_version_pattern, content, re.DOTALL)
    
    if not match:
        logging.error("Could not find detect_os_version method in os_probe.py")
        return False
    
    # Original method code
    original_method = match.group(0)
    
    # Modified method with beta version detection
    modified_method = """def detect_os_version(self) -> str:
        """
        Detect the booted OS version

        Returns:
            str: OS version (ex. 12.0)
        """

        result = subprocess.run(["/usr/bin/sw_vers", "-productVersion"], stdout=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError("Failed to detect OS version")
        
        os_version = result.stdout.decode().strip()
        
        # Add detection for macOS beta versions
        if os_version.startswith("26."):
            logging.info(f"Detected macOS Beta version: {os_version}")
            if os_version == "26.3":
                return "macOS Beta 3"
            elif os_version == "26.2":
                return "macOS Beta 2"
            elif os_version == "26.1":
                return "macOS Beta 1"
            elif os_version.startswith("26.0") or os_version.startswith("26."):
                return "macOS Beta"
        
        return os_version"""
    
    # Replace the original method with the modified one
    patched_content = content.replace(original_method, modified_method)
    
    # Write the patched content back to the file
    with open(file_path, 'w') as f:
        f.write(patched_content)
    
    logging.info(f"Successfully patched {file_path} with macOS beta version detection")
    return True

def patch_os_data_file(file_path):
    """
    Patch the os_data.py file to add macOS beta versions to the enum
    
    Parameters:
        file_path (str): Path to the os_data.py file
    
    Returns:
        bool: True if patching was successful, False otherwise
    """
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return False
    
    # Read the original file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Create backup
    with open(f"{file_path}.bak", 'w') as f:
        f.write(content)
    
    # Find the os_data class definition
    os_data_class_pattern = r'class os_data\(enum\.IntEnum\):(.*?)max_os ='
    match = re.search(os_data_class_pattern, content, re.DOTALL)
    
    if not match:
        logging.error("Could not find os_data class in os_data.py")
        return False
    
    # Original class content
    original_class = match.group(0)
    
    # Check if beta versions are already added
    if "macos_beta =" in original_class:
        logging.info("macOS beta versions already added to os_data.py")
        return True
    
    # Modified class with beta versions
    modified_class = original_class + """    macos_beta =     26
    macos_beta_1 =   26
    macos_beta_2 =   26
    macos_beta_3 =   26
    """
    
    # Replace the original class with the modified one
    patched_content = content.replace(original_class, modified_class)
    
    # Write the patched content back to the file
    with open(file_path, 'w') as f:
        f.write(patched_content)
    
    logging.info(f"Successfully patched {file_path} with macOS beta version definitions")
    return True

def main():
    """
    Main function to apply patches
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Get the directory of the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Default paths (can be overridden by command line arguments)
    os_probe_path = os.path.join(script_dir, "opencore_legacy_patcher/detections/os_probe.py")
    os_data_path = os.path.join(script_dir, "opencore_legacy_patcher/datasets/os_data.py")
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        os_probe_path = sys.argv[1]
    if len(sys.argv) > 2:
        os_data_path = sys.argv[2]
    
    logging.info(f"Patching os_probe.py at: {os_probe_path}")
    if patch_os_probe_file(os_probe_path):
        logging.info("Successfully patched os_probe.py")
    else:
        logging.error("Failed to patch os_probe.py")
        return 1
    
    logging.info(f"Patching os_data.py at: {os_data_path}")
    if patch_os_data_file(os_data_path):
        logging.info("Successfully patched os_data.py")
    else:
        logging.error("Failed to patch os_data.py")
        return 1
    
    logging.info("All patches applied successfully")
    return 0

if __name__ == "__main__":
    sys.exit(main())
