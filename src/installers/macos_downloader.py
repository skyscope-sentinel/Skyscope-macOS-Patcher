#!/usr/bin/env python3
"""
macos_downloader.py
Skyscope macOS Patcher - macOS Installer Downloader

Downloads official macOS installer images (IPSW) for Sequoia and Tahoe
from Apple servers with version detection, progress tracking, verification, and caching.

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
from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, List, Optional, Tuple, Union

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
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'macos_downloader.log'))
    ]
)
logger = logging.getLogger('MacOSDownloader')

# Constants
APPLE_CATALOGS = {
    "RELEASE": "https://swscan.apple.com/content/catalogs/others/index-14-13-12-10.16-10.15-10.14-10.13-10.12-10.11-10.10-10.9-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog",
    "BETA": "https://swscan.apple.com/content/catalogs/others/index-14seed-13seed-12seed-10.16seed-10.15seed-10.14seed-10.13seed-10.12seed-10.11seed-10.10seed-10.9seed-mountainlionseed-lionseed-snowleopardseed-leopardseed.merged-1.sucatalog"
}

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

# Default cache directory
DEFAULT_CACHE_DIR = os.path.expanduser("~/Library/Caches/SkyscopePatcher/InstallerCache")

# Supported architectures
SUPPORTED_ARCHITECTURES = ["x86_64", "arm64"]

class MacOSDownloader:
    """Class to handle downloading of macOS installers"""
    
    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, include_betas: bool = False):
        """
        Initialize the downloader
        
        Args:
            cache_dir: Directory to store downloaded files
            include_betas: Whether to include beta versions in search
        """
        self.cache_dir = cache_dir
        self.include_betas = include_betas
        self.catalog_data = {}
        self.available_versions = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Skyscope-Patcher/1.0 (Compatible; macOS)'
        })
        
        # Create cache directory if it doesn't exist
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Create metadata directory
        self.metadata_dir = os.path.join(self.cache_dir, 'metadata')
        os.makedirs(self.metadata_dir, exist_ok=True)
        
        # Load cached metadata if available
        self.metadata_file = os.path.join(self.metadata_dir, 'versions.json')
        self.load_metadata()
    
    def load_metadata(self) -> None:
        """Load cached metadata if available"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r') as f:
                    data = json.load(f)
                    
                # Check if metadata is recent (less than 24 hours old)
                if 'timestamp' in data and (time.time() - data['timestamp']) < 86400:
                    self.available_versions = data.get('versions', {})
                    logger.info(f"Loaded {len(self.available_versions)} versions from cache")
                    return
            except Exception as e:
                logger.warning(f"Failed to load cached metadata: {e}")
        
        # If we get here, we need to refresh the metadata
        logger.info("Cached metadata not available or expired, will fetch fresh data")
    
    def save_metadata(self) -> None:
        """Save metadata to cache"""
        try:
            data = {
                'versions': self.available_versions,
                'timestamp': time.time(),
                'generated': datetime.now().isoformat()
            }
            
            with open(self.metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved metadata with {len(self.available_versions)} versions")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
    
    def fetch_catalog(self, catalog_type: str = "RELEASE") -> bool:
        """
        Fetch the Apple software catalog
        
        Args:
            catalog_type: Type of catalog to fetch (RELEASE or BETA)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if catalog_type not in APPLE_CATALOGS:
            logger.error(f"Invalid catalog type: {catalog_type}")
            return False
        
        catalog_url = APPLE_CATALOGS[catalog_type]
        logger.info(f"Fetching {catalog_type} catalog from {catalog_url}")
        
        try:
            response = self.session.get(catalog_url)
            response.raise_for_status()
            
            # Parse the catalog (it's a property list in XML format)
            catalog_content = response.text
            
            # Extract product information using regex
            # This is a simplified approach; in a real implementation,
            # we would use a proper plist parser
            product_pattern = r'<key>([^<]+)</key>\s*<dict>(.*?)</dict>'
            products = re.findall(product_pattern, catalog_content, re.DOTALL)
            
            self.catalog_data[catalog_type] = {}
            
            for product_id, product_info in products:
                # Look for macOS installers
                if self._is_macos_installer(product_info):
                    self.catalog_data[catalog_type][product_id] = self._parse_product_info(product_info)
            
            logger.info(f"Found {len(self.catalog_data[catalog_type])} products in {catalog_type} catalog")
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch catalog: {e}")
            return False
    
    def _is_macos_installer(self, product_info: str) -> bool:
        """
        Check if a product is a macOS installer
        
        Args:
            product_info: Product information string
            
        Returns:
            bool: True if it's a macOS installer, False otherwise
        """
        # Check for IPSW file extension and macOS version patterns
        return '.ipsw' in product_info and any(
            re.search(version_info['build_pattern'], product_info)
            for version_info in MACOS_VERSIONS.values()
        )
    
    def _parse_product_info(self, product_info: str) -> Dict:
        """
        Parse product information from catalog
        
        Args:
            product_info: Product information string
            
        Returns:
            Dict: Parsed product information
        """
        result = {
            'title': '',
            'version': '',
            'build': '',
            'post_date': '',
            'packages': []
        }
        
        # Extract title
        title_match = re.search(r'<key>title</key>\s*<string>([^<]+)</string>', product_info)
        if title_match:
            result['title'] = title_match.group(1)
        
        # Extract version
        version_match = re.search(r'<key>version</key>\s*<string>([^<]+)</string>', product_info)
        if version_match:
            result['version'] = version_match.group(1)
        
        # Extract build
        # Look for patterns like 15A123, 16B456, etc.
        for version_info in MACOS_VERSIONS.values():
            build_match = re.search(version_info['build_pattern'], product_info)
            if build_match:
                result['build'] = build_match.group(0)
                break
        
        # Extract post date
        date_match = re.search(r'<key>PostDate</key>\s*<date>([^<]+)</date>', product_info)
        if date_match:
            result['post_date'] = date_match.group(1)
        
        # Extract packages (IPSW files)
        package_pattern = r'<key>URL</key>\s*<string>([^<]+\.ipsw)</string>\s*.*?<key>Size</key>\s*<integer>(\d+)</integer>\s*.*?<key>SHA1</key>\s*<string>([^<]+)</string>'
        packages = re.findall(package_pattern, product_info, re.DOTALL)
        
        for url, size, sha1 in packages:
            # Extract architecture from URL or filename
            arch = "unknown"
            if "arm64" in url.lower():
                arch = "arm64"
            elif "x86_64" in url.lower() or "intel" in url.lower():
                arch = "x86_64"
            
            result['packages'].append({
                'url': url,
                'size': int(size),
                'sha1': sha1,
                'architecture': arch
            })
        
        return result
    
    def find_available_versions(self) -> Dict:
        """
        Find all available macOS versions in the catalogs
        
        Returns:
            Dict: Available versions by macOS version name
        """
        # If we already have data and it's recent, use it
        if self.available_versions:
            return self.available_versions
        
        # Fetch catalogs if needed
        if not self.catalog_data.get("RELEASE"):
            self.fetch_catalog("RELEASE")
        
        if self.include_betas and not self.catalog_data.get("BETA"):
            self.fetch_catalog("BETA")
        
        # Process catalogs to find available versions
        self.available_versions = {}
        
        for catalog_type, products in self.catalog_data.items():
            for product_id, product_info in products.items():
                # Determine macOS version
                macos_version = None
                for version_name, version_info in MACOS_VERSIONS.items():
                    if product_info['build'].startswith(version_info['min_build']):
                        macos_version = version_name
                        break
                
                if not macos_version:
                    continue
                
                # Skip if no valid packages
                if not product_info['packages']:
                    continue
                
                # Create entry for this macOS version if it doesn't exist
                if macos_version not in self.available_versions:
                    self.available_versions[macos_version] = []
                
                # Add this product
                self.available_versions[macos_version].append({
                    'product_id': product_id,
                    'title': product_info['title'],
                    'version': product_info['version'],
                    'build': product_info['build'],
                    'post_date': product_info['post_date'],
                    'catalog_type': catalog_type,
                    'packages': product_info['packages']
                })
        
        # Sort versions by build number (newest first)
        for version_name in self.available_versions:
            self.available_versions[version_name].sort(
                key=lambda x: x['build'],
                reverse=True
            )
        
        # Save metadata
        self.save_metadata()
        
        return self.available_versions
    
    def list_versions(self, macos_version: Optional[str] = None) -> None:
        """
        List available versions
        
        Args:
            macos_version: Specific macOS version to list, or None for all
        """
        versions = self.find_available_versions()
        
        if not versions:
            print("No macOS versions found")
            return
        
        if macos_version and macos_version in versions:
            versions = {macos_version: versions[macos_version]}
        
        for version_name, products in versions.items():
            print(f"\n{MACOS_VERSIONS[version_name]['marketing_name']} (macOS {MACOS_VERSIONS[version_name]['version']}):")
            
            for idx, product in enumerate(products):
                print(f"  {idx + 1}. {product['title']} ({product['version']})")
                print(f"     Build: {product['build']}")
                print(f"     Date: {product['post_date']}")
                
                for package in product['packages']:
                    size_gb = package['size'] / (1024 * 1024 * 1024)
                    print(f"     {package['architecture']} IPSW: {size_gb:.2f} GB")
                
                print()
    
    def download_installer(self, 
                          macos_version: str, 
                          build: Optional[str] = None, 
                          architecture: str = "x86_64", 
                          output_dir: Optional[str] = None) -> Optional[str]:
        """
        Download a macOS installer
        
        Args:
            macos_version: macOS version to download (e.g., "sequoia", "tahoe")
            build: Specific build to download, or None for latest
            architecture: Target architecture ("x86_64" or "arm64")
            output_dir: Directory to save the installer, or None for cache dir
            
        Returns:
            str: Path to downloaded file, or None if download failed
        """
        if architecture not in SUPPORTED_ARCHITECTURES:
            logger.error(f"Unsupported architecture: {architecture}")
            return None
        
        # Find available versions
        versions = self.find_available_versions()
        
        if macos_version not in versions:
            logger.error(f"macOS version '{macos_version}' not found")
            return None
        
        products = versions[macos_version]
        
        # Find the requested build or use the latest
        target_product = None
        
        if build:
            for product in products:
                if product['build'] == build:
                    target_product = product
                    break
            
            if not target_product:
                logger.error(f"Build '{build}' not found for {macos_version}")
                return None
        else:
            # Use the latest build
            target_product = products[0]
        
        # Find package for requested architecture
        target_package = None
        
        for package in target_product['packages']:
            if package['architecture'] == architecture:
                target_package = package
                break
        
        if not target_package:
            logger.error(f"No {architecture} package found for {macos_version} build {target_product['build']}")
            return None
        
        # Determine output directory
        if not output_dir:
            output_dir = os.path.join(self.cache_dir, macos_version, target_product['build'])
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Determine output filename
        url_path = urlparse(target_package['url']).path
        filename = os.path.basename(url_path)
        output_path = os.path.join(output_dir, filename)
        
        # Check if file already exists and is valid
        if os.path.exists(output_path):
            if self._verify_file(output_path, target_package['sha1']):
                logger.info(f"File already exists and is valid: {output_path}")
                return output_path
            else:
                logger.warning(f"File exists but is invalid, will re-download: {output_path}")
        
        # Download the file
        logger.info(f"Downloading {filename} ({target_package['size'] / (1024*1024*1024):.2f} GB)...")
        
        temp_path = output_path + ".download"
        
        try:
            # Check if we can resume a previous download
            headers = {}
            if os.path.exists(temp_path):
                temp_size = os.path.getsize(temp_path)
                if temp_size > 0 and temp_size < target_package['size']:
                    headers['Range'] = f'bytes={temp_size}-'
                    logger.info(f"Resuming download from {temp_size / (1024*1024):.2f} MB")
            
            # Start the download
            response = self.session.get(target_package['url'], headers=headers, stream=True)
            response.raise_for_status()
            
            # Determine mode based on whether we're resuming
            mode = 'ab' if 'Range' in headers else 'wb'
            total_size = int(response.headers.get('content-length', 0))
            
            # Adjust for resume
            if 'Range' in headers:
                total_size += os.path.getsize(temp_path)
            else:
                total_size = target_package['size']
            
            # Download with progress bar
            with open(temp_path, mode) as f:
                with tqdm(
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=filename
                ) as pbar:
                    # Update progress bar with existing file size if resuming
                    if 'Range' in headers:
                        pbar.update(os.path.getsize(temp_path))
                    
                    # Download in chunks
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            
            # Verify the download
            logger.info("Verifying download...")
            if self._verify_file(temp_path, target_package['sha1']):
                # Rename temp file to final filename
                os.rename(temp_path, output_path)
                logger.info(f"Download complete and verified: {output_path}")
                return output_path
            else:
                logger.error("Download verification failed")
                return None
                
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None
    
    def _verify_file(self, file_path: str, expected_sha1: str) -> bool:
        """
        Verify a file using its SHA1 hash
        
        Args:
            file_path: Path to the file
            expected_sha1: Expected SHA1 hash
            
        Returns:
            bool: True if file is valid, False otherwise
        """
        try:
            sha1 = hashlib.sha1()
            
            with open(file_path, 'rb') as f:
                # Read and update hash in chunks to avoid loading large files into memory
                for chunk in iter(lambda: f.read(4096), b''):
                    sha1.update(chunk)
            
            file_sha1 = sha1.hexdigest()
            
            if file_sha1.lower() == expected_sha1.lower():
                return True
            else:
                logger.warning(f"SHA1 mismatch: expected {expected_sha1}, got {file_sha1}")
                return False
                
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False
    
    def create_installer_json(self, installer_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Create a JSON file with installer information
        
        Args:
            installer_path: Path to the installer
            output_path: Path to save the JSON file, or None for same directory
            
        Returns:
            str: Path to the JSON file, or None if failed
        """
        try:
            if not os.path.exists(installer_path):
                logger.error(f"Installer not found: {installer_path}")
                return None
            
            # Extract information from filename and path
            filename = os.path.basename(installer_path)
            directory = os.path.dirname(installer_path)
            
            # Determine macOS version and build from path
            path_parts = directory.split(os.sep)
            macos_version = None
            build = None
            
            for part in path_parts:
                if part in MACOS_VERSIONS:
                    macos_version = part
                elif any(part.startswith(v['min_build']) for v in MACOS_VERSIONS.values()):
                    build = part
            
            if not macos_version or not build:
                # Try to extract from filename
                for version_name, version_info in MACOS_VERSIONS.items():
                    if re.search(version_info['build_pattern'], filename):
                        macos_version = version_name
                        build_match = re.search(version_info['build_pattern'], filename)
                        if build_match:
                            build = build_match.group(0)
                        break
            
            if not macos_version or not build:
                logger.error("Could not determine macOS version and build from path or filename")
                return None
            
            # Determine architecture from filename
            arch = "unknown"
            if "arm64" in filename.lower():
                arch = "arm64"
            elif "x86_64" in filename.lower() or "intel" in filename.lower():
                arch = "x86_64"
            
            # Get file size and hash
            size = os.path.getsize(installer_path)
            
            # Calculate SHA1 hash
            sha1 = hashlib.sha1()
            with open(installer_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha1.update(chunk)
            file_sha1 = sha1.hexdigest()
            
            # Create JSON data
            data = {
                "installer_path": installer_path,
                "filename": filename,
                "macos_version": macos_version,
                "marketing_name": MACOS_VERSIONS[macos_version]['marketing_name'],
                "version_number": MACOS_VERSIONS[macos_version]['version'],
                "build": build,
                "architecture": arch,
                "size": size,
                "size_gb": size / (1024 * 1024 * 1024),
                "sha1": file_sha1,
                "timestamp": time.time(),
                "date": datetime.now().isoformat()
            }
            
            # Determine output path
            if not output_path:
                output_path = os.path.join(directory, f"{os.path.splitext(filename)[0]}.json")
            
            # Write JSON file
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Created installer JSON: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to create installer JSON: {e}")
            return None
    
    def clean_cache(self, keep_latest: bool = True) -> bool:
        """
        Clean the cache directory
        
        Args:
            keep_latest: Whether to keep the latest version of each macOS version
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get all versions
            versions = self.find_available_versions()
            
            # Track what to keep
            keep_files = set()
            
            if keep_latest:
                # Find the latest build for each macOS version
                for version_name, products in versions.items():
                    if products:
                        latest_build = products[0]['build']
                        build_dir = os.path.join(self.cache_dir, version_name, latest_build)
                        
                        if os.path.exists(build_dir):
                            for filename in os.listdir(build_dir):
                                keep_files.add(os.path.join(build_dir, filename))
            
            # Clean up files
            total_freed = 0
            
            for version_name in versions.keys():
                version_dir = os.path.join(self.cache_dir, version_name)
                
                if not os.path.exists(version_dir):
                    continue
                
                for build_name in os.listdir(version_dir):
                    build_dir = os.path.join(version_dir, build_name)
                    
                    if not os.path.isdir(build_dir):
                        continue
                    
                    for filename in os.listdir(build_dir):
                        file_path = os.path.join(build_dir, filename)
                        
                        if file_path not in keep_files:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            total_freed += file_size
                    
                    # Remove empty directories
                    if not os.listdir(build_dir):
                        os.rmdir(build_dir)
            
            logger.info(f"Cleaned cache, freed {total_freed / (1024*1024*1024):.2f} GB")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clean cache: {e}")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Download macOS installers')
    
    parser.add_argument('--version', choices=list(MACOS_VERSIONS.keys()),
                        help='macOS version to download')
    parser.add_argument('--build', help='Specific build to download')
    parser.add_argument('--arch', choices=SUPPORTED_ARCHITECTURES, default='x86_64',
                        help='Target architecture (default: x86_64)')
    parser.add_argument('--output-dir', help='Output directory')
    parser.add_argument('--cache-dir', default=DEFAULT_CACHE_DIR,
                        help=f'Cache directory (default: {DEFAULT_CACHE_DIR})')
    parser.add_argument('--include-betas', action='store_true',
                        help='Include beta versions')
    parser.add_argument('--list', action='store_true',
                        help='List available versions')
    parser.add_argument('--clean-cache', action='store_true',
                        help='Clean the cache directory')
    parser.add_argument('--keep-latest', action='store_true',
                        help='Keep the latest version when cleaning cache')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set log level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Create downloader
    downloader = MacOSDownloader(cache_dir=args.cache_dir, include_betas=args.include_betas)
    
    # Handle commands
    if args.list:
        downloader.list_versions(args.version)
        return 0
    
    if args.clean_cache:
        success = downloader.clean_cache(keep_latest=args.keep_latest)
        return 0 if success else 1
    
    if args.version:
        # Download installer
        installer_path = downloader.download_installer(
            macos_version=args.version,
            build=args.build,
            architecture=args.arch,
            output_dir=args.output_dir
        )
        
        if installer_path:
            # Create JSON info file
            downloader.create_installer_json(installer_path)
            print(f"\nInstaller downloaded to: {installer_path}")
            return 0
        else:
            print("\nDownload failed")
            return 1
    
    # If no command specified, show help
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
