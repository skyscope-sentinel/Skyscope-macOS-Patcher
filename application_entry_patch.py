#!/usr/bin/env python3
"""
application_entry_patch.py: Patch OpenCore Legacy Patcher's application_entry.py 
to better handle macOS beta versions (26.0-26.3)

This script adds enhanced detection and handling for macOS beta versions,
ensuring a smooth user experience when running on pre-release macOS builds.
"""

import os
import re
import sys
import logging
import shutil
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class ApplicationEntryPatcher:
    """
    Patches the application_entry.py file to better handle macOS beta versions
    """
    
    def __init__(self, file_path):
        """
        Initialize the patcher with the path to application_entry.py
        
        Parameters:
            file_path (str): Path to application_entry.py
        """
        self.file_path = file_path
        self.backup_path = f"{file_path}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
        self.content = None
        
    def read_file(self):
        """
        Read the content of application_entry.py
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(self.file_path, 'r') as f:
                self.content = f.read()
            return True
        except Exception as e:
            logging.error(f"Failed to read file: {e}")
            return False
            
    def backup_file(self):
        """
        Create a backup of the original file
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            shutil.copy2(self.file_path, self.backup_path)
            logging.info(f"Backup created at: {self.backup_path}")
            return True
        except Exception as e:
            logging.error(f"Failed to create backup: {e}")
            return False
            
    def patch_generate_base_data(self):
        """
        Patch the _generate_base_data method to handle macOS beta versions
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.content:
            logging.error("No file content loaded")
            return False
            
        # Find the _generate_base_data method
        pattern = r'(def _generate_base_data\(self\).*?)(# Generate computer data)'
        match = re.search(pattern, self.content, re.DOTALL)
        
        if not match:
            logging.error("Could not find _generate_base_data method")
            return False
            
        original_method_start = match.group(1)
        after_method = match.group(2)
        
        # Create the patched method with beta version handling
        beta_handler = """
        # Enhanced macOS Beta version handling (SkyScope patch)
        if "Beta" in self.constants.detected_os_version:
            logging.info(f"Detected macOS Beta version: {self.constants.detected_os_version}")
            # Set OS version for compatibility with beta releases
            if self.constants.detected_os_build.startswith("26"):
                beta_version = 26.0  # Default to 26.0 for all beta versions
                
                # More specific beta version handling
                if "26.3" in self.constants.detected_os_version:
                    beta_version = 26.3
                    logging.info("Setting compatibility for macOS Beta 3")
                elif "26.2" in self.constants.detected_os_version:
                    beta_version = 26.2
                    logging.info("Setting compatibility for macOS Beta 2")
                elif "26.1" in self.constants.detected_os_version:
                    beta_version = 26.1
                    logging.info("Setting compatibility for macOS Beta 1")
                else:
                    logging.info("Setting compatibility for macOS Beta")
                
                # Ensure we have proper support in constants
                from .datasets import os_data
                if not hasattr(os_data.os_data, "macos_beta"):
                    setattr(os_data.os_data, "macos_beta", beta_version)
                    
                # Add to legacy acceleration support list if not already there
                if beta_version not in self.constants.legacy_accel_support:
                    self.constants.legacy_accel_support.append(beta_version)
                    logging.info(f"Added {beta_version} to legacy acceleration support list")
                    
                # Set detected OS to a value that will work with existing code
                # This prevents errors in code that checks for specific OS versions
                self.constants.detected_os = 26
                logging.info(f"Set detected_os to {self.constants.detected_os} for compatibility")

        """
        
        # Insert the beta handler after OS detection but before computer data generation
        patched_method = original_method_start + beta_handler + after_method
        self.content = self.content.replace(match.group(0), patched_method)
        
        return True
        
    def patch_init_method(self):
        """
        Patch the __init__ method to add beta version warning if needed
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.content:
            logging.error("No file content loaded")
            return False
            
        # Find the __init__ method
        pattern = r'(def __init__\(self\).*?)(self._generate_base_data\(\))'
        match = re.search(pattern, self.content, re.DOTALL)
        
        if not match:
            logging.error("Could not find __init__ method")
            return False
            
        original_init = match.group(1)
        generate_base_data_call = match.group(2)
        
        # Add beta version flag
        beta_flag = """
        # Flag for beta version detection (SkyScope patch)
        self.is_beta_os = False
        
        """
        
        # Insert the beta flag before _generate_base_data call
        patched_init = original_init + beta_flag + generate_base_data_call
        self.content = self.content.replace(match.group(0), patched_init)
        
        return True
        
    def add_beta_helper_method(self):
        """
        Add a helper method for beta version compatibility
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.content:
            logging.error("No file content loaded")
            return False
            
        # Find the OpenCoreLegacyPatcher class
        pattern = r'(class OpenCoreLegacyPatcher:.*?)(def main\(\):)'
        match = re.search(pattern, self.content, re.DOTALL)
        
        if not match:
            logging.error("Could not find OpenCoreLegacyPatcher class")
            return False
            
        class_content = match.group(1)
        main_function = match.group(2)
        
        # Create the helper method
        helper_method = """
    def _handle_beta_compatibility(self) -> None:
        """
        Special handler for macOS beta versions to ensure compatibility
        This method is called when a beta OS is detected to configure
        appropriate settings and provide user feedback
        """
        if "Beta" in self.constants.detected_os_version:
            self.is_beta_os = True
            logging.info("Configuring for macOS Beta compatibility")
            
            # Set special flags for beta compatibility
            self.constants.force_latest_psp = True
            
            # Log detailed information for troubleshooting
            logging.info(f"Beta OS Version: {self.constants.detected_os_version}")
            logging.info(f"Beta OS Build: {self.constants.detected_os_build}")
            logging.info(f"Detected OS Major: {self.constants.detected_os}")
            logging.info(f"Detected OS Minor: {self.constants.detected_os_minor}")
            
            # Check for critical components
            if not hasattr(self.constants, "legacy_accel_support"):
                logging.warning("Legacy acceleration support list not found, creating...")
                self.constants.legacy_accel_support = []
            
            # Ensure beta version is in legacy_accel_support
            beta_version = 26.0  # Default
            if self.constants.detected_os not in self.constants.legacy_accel_support:
                self.constants.legacy_accel_support.append(self.constants.detected_os)
                logging.info(f"Added {self.constants.detected_os} to legacy acceleration support")


"""
        
        # Add the helper method to the class
        patched_class = class_content + helper_method + main_function
        self.content = self.content.replace(match.group(0), patched_class)
        
        return True
        
    def update_generate_base_data_call(self):
        """
        Update the _generate_base_data method to call our beta helper
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.content:
            logging.error("No file content loaded")
            return False
            
        # Find where we detect OS version and add the beta handler call
        pattern = r'(self\.constants\.detected_os_version = os_data\.detect_os_version\(\))'
        
        beta_handler_call = """
        self.constants.detected_os_version = os_data.detect_os_version()
        
        # Call beta compatibility handler if needed (SkyScope patch)
        if "Beta" in self.constants.detected_os_version:
            self._handle_beta_compatibility()
        """
        
        # Replace the OS version detection with our enhanced version
        self.content = re.sub(pattern, beta_handler_call, self.content)
        
        return True
        
    def write_patched_file(self):
        """
        Write the patched content back to the file
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(self.file_path, 'w') as f:
                f.write(self.content)
            logging.info(f"Successfully wrote patched file to: {self.file_path}")
            return True
        except Exception as e:
            logging.error(f"Failed to write patched file: {e}")
            return False
            
    def patch(self):
        """
        Apply all patches to the file
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not os.path.exists(self.file_path):
            logging.error(f"File not found: {self.file_path}")
            return False
            
        if not self.read_file():
            return False
            
        if not self.backup_file():
            return False
            
        success = (
            self.patch_init_method() and
            self.add_beta_helper_method() and
            self.patch_generate_base_data() and
            self.update_generate_base_data_call() and
            self.write_patched_file()
        )
        
        if success:
            logging.info("Successfully applied all patches")
        else:
            logging.error("Failed to apply all patches")
            
        return success

def main():
    """
    Main function to apply the patch
    """
    # Check command line arguments
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} path/to/application_entry.py")
        return 1
        
    file_path = sys.argv[1]
    
    logging.info(f"Patching application_entry.py at: {file_path}")
    patcher = ApplicationEntryPatcher(file_path)
    
    if patcher.patch():
        logging.info("Patch applied successfully")
        return 0
    else:
        logging.error("Failed to apply patch")
        return 1

if __name__ == "__main__":
    sys.exit(main())
