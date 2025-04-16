#!/usr/bin/env python3
"""
mylar2kapowarr.py

A script to migrate comic metadata and file information from a Mylar3 instance into Kapowarr.
It queries the Mylar API to get information about comics and their files, then
calls the Kapowarr API to add the corresponding comic volumes and copy files to Kapowarr's folder structure.
"""

import argparse
import json
import logging
import os
import re
import shutil
import time
import requests
from typing import Dict, List, Optional, Tuple, Any, Union

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("mylar2kapowarr")


class MylarAPI:
    def __init__(self, base_url: str, api_key: str):
        """Initialize the Mylar API client."""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()

    def _make_request(self, cmd: str, params: Dict = None) -> Dict:
        """Make a request to the Mylar API."""
        url = f"{self.base_url}/api"
        all_params = {"apikey": self.api_key, "cmd": cmd}
        if params:
            all_params.update(params)
        
        logger.info(f"Fetching from Mylar: {url} with params {all_params}")
        try:
            response = self.session.get(url, params=all_params)
            logger.info(f"Mylar API response status code: {response.status_code}")
            
            # Print raw response text for debugging
            logger.info(f"Mylar API raw response: {response.text[:500]}...")
            
            response.raise_for_status()
            data = response.json()
            
            # Log the full response at DEBUG level
            logger.debug(f"Mylar response JSON: {data}")
            
            # Log a summary at INFO level
            if "success" in data:
                logger.info(f"Mylar API success: {data.get('success')}")
            if "data" in data:
                if isinstance(data["data"], list):
                    logger.info(f"Mylar API returned {len(data['data'])} items")
                elif isinstance(data["data"], dict):
                    logger.info(f"Mylar API returned data keys: {list(data['data'].keys())}")
            
            return data
        except Exception as e:
            logger.error(f"Failed to make request to Mylar API: {e}")
            return {"success": False, "data": []}
    
    def download_issue(self, issue_id: str, destination_path: str) -> str:
        """
        Download a comic issue directly from Mylar's API and save it to the provided destination path.
        
        Args:
            issue_id: The issue ID in Mylar
            destination_path: The directory where the file should be saved
            
        Returns:
            The path to the downloaded file, or empty string if download failed
        """
        logger.info(f"Downloading issue {issue_id} from Mylar API")
        
        # Create the download URL
        url = f"{self.base_url}/api"
        params = {
            "apikey": self.api_key,
            "cmd": "downloadIssue",
            "id": issue_id
        }
        
        try:
            # Make a request to download the file
            response = self.session.get(url, params=params, stream=True)
            
            # Check if the response is successful
            response.raise_for_status()
            
            # Check if we're getting a file (binary data) or an error response (typically JSON)
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                # This is likely an error response
                error_data = response.json()
                logger.error(f"Mylar API returned an error: {error_data}")
                return ""
            
            # Get the filename from the Content-Disposition header if available
            filename = ""
            content_disposition = response.headers.get('Content-Disposition')
            if content_disposition:
                filename_match = re.search(r'filename="?([^"]+)"?', content_disposition)
                if filename_match:
                    filename = filename_match.group(1)
            
            # If no filename is provided, use a default format
            if not filename:
                filename = f"issue_{issue_id}.cbz"
            
            # Make sure the destination directory exists
            os.makedirs(destination_path, exist_ok=True)
            
            # Path to save the file
            file_path = os.path.join(destination_path, filename)
            
            # Save the file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verify the file was written successfully
            if not os.path.exists(file_path):
                logger.error(f"File was not created at {file_path}")
                return ""
                
            # Verify the file has content
            if os.path.getsize(file_path) == 0:
                logger.error(f"File was created but is empty: {file_path}")
                os.remove(file_path)
                return ""
            
            logger.info(f"Successfully downloaded issue {issue_id} to {file_path}")
            
            # Set appropriate permissions
            os.chmod(file_path, 0o644)  # rw-r--r--
            
            return file_path
        
        except Exception as e:
            logger.error(f"Failed to download issue {issue_id}: {e}")
            return ""

    def get_comics(self, cmd: str = "getComics") -> List[Dict]:
        """
        Fetch the list of comic series from Mylar.
        
        Args:
            cmd: The API command to use. Options include:
                - 'getComics' (for older Mylar versions)
                - 'getSeries' (for newer Mylar3 versions)
                - 'getIndex' (alternative approach)
        
        Returns:
            A list of comics from the Mylar API
        """
        logger.info(f"Fetching comics from Mylar using '{cmd}' command")
        data = self._make_request(cmd)
        
        # Try to extract comics from response based on the command
        comics = []
        
        if cmd == "getComics" or cmd == "getSeries":
            comics = data.get("data", [])
        elif cmd == "getIndex":
            # getIndex directly returns a list in the data field
            if isinstance(data.get("data"), list):
                comics = data.get("data", [])
            # Fallback for older versions that might have a different structure
            elif isinstance(data.get("data"), dict):
                comics_data = data.get("data", {}).get("comics", [])
                if comics_data:
                    comics = comics_data
        
        if not comics:
            logger.info(f"No comics were found in the Mylar response using '{cmd}' command.")
        else:
            logger.info(f"Found {len(comics)} comics in Mylar response.")
            
            # Log some sample data to help understand the structure
            if comics and len(comics) > 0:
                sample = comics[0]
                logger.info(f"Sample comic data format: {list(sample.keys())}")
        
        return comics
    
    def get_comic_info(self, comic_id: str) -> Dict:
        """
        Fetch detailed information for a specific comic series.
        """
        params = {"id": comic_id}
        data = self._make_request("getComic", params)
        return data.get("data", {})

    def get_issues(self, comic_id: str) -> List[Dict]:
        """
        Fetch the list of issues for a comic series.
        This information is included in the getComic response.
        """
        comic_data = self.get_comic_info(comic_id)
        return comic_data.get("issues", [])
    
    def get_wanted(self) -> Dict:
        """
        Fetch the list of wanted issues from Mylar.
        """
        params = {"issues": "True", "annuals": "True"}
        data = self._make_request("getWanted", params)
        return data.get("data", {})


class KapowarrAPI:
    def __init__(self, base_url: str, api_key: str):
        """Initialize the Kapowarr API client."""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        
        # Verify API connection and authentication
        self._check_auth()

    def _check_auth(self) -> None:
        """
        Verify that we can authenticate to the Kapowarr API.
        """
        url = f"{self.base_url}/api/auth/check"
        try:
            response = self.session.post(url, params={"api_key": self.api_key})
            response.raise_for_status()
            logger.info("Successfully authenticated to Kapowarr API")
        except Exception as e:
            logger.error(f"Failed to authenticate to Kapowarr API: {e}")
            raise

    def _make_request(self, method: str, endpoint: str, params: Dict = None, json_data: Dict = None) -> Dict:
        """
        Make a request to the Kapowarr API.
        """
        url = f"{self.base_url}/api/{endpoint}"
        all_params = {"api_key": self.api_key}
        if params:
            all_params.update(params)
        
        headers = {"Content-Type": "application/json"} if json_data else None
        
        logger.debug(f"Making {method} request to {url} with params {all_params}")
        if json_data:
            logger.debug(f"Request body: {json_data}")
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=all_params,
                headers=headers,
                json=json_data
            )
            
            # Log status code at debug level
            logger.debug(f"Response status code: {response.status_code}")
            
            # Try to get response text
            try:
                response_text = response.text
                # Log full response at DEBUG level only
                logger.debug(f"Response text: {response_text}")
            except Exception:
                response_text = "<unable to get response text>"
            
            # Raise exception for HTTP errors
            response.raise_for_status()
            
            # Parse and return JSON
            try:
                return response.json()
            except Exception as e:
                logger.error(f"Failed to parse JSON response from Kapowarr: {e}")
                logger.error(f"Response text: {response_text}")
                return {"error": "Invalid JSON response", "result": {}}
                
        except Exception as e:
            logger.error(f"Failed to make request to Kapowarr API: {e}")
            raise

    def get_root_folders(self) -> List[Dict]:
        """Get the list of root folders configured in Kapowarr."""
        response = self._make_request("GET", "rootfolder")
        return response.get("result", [])

    def get_all_volumes(self) -> List[Dict]:
        """
        Get all volumes from Kapowarr.
        """
        response = self._make_request("GET", "volumes", params={"sort": "TITLE"})
        return response.get("result", [])

    def is_volume_added(self, comicvine_id: str) -> bool:
        """
        Check if a volume with the given ComicVine ID is already added to Kapowarr.
        """
        volumes = self.get_all_volumes()
        return any(str(vol.get("comicvine_id")) == str(comicvine_id) for vol in volumes)

    def add_volume(self, volume_data: Dict) -> Dict:
        """
        Add a new comic volume to Kapowarr using the API.
        
        Returns:
            The result from the API, or a dict with 'error' if there was an error.
            In case of 'VolumeAlreadyAdded' error, returns {'error': 'VolumeAlreadyAdded'}
        """
        # First check if the volume is already added
        comicvine_id = volume_data.get("comicvine_id")
        if comicvine_id and self.is_volume_added(comicvine_id):
            logger.info(f"Volume with ComicVine ID {comicvine_id} is already added to Kapowarr")
            return {"error": "VolumeAlreadyAdded"}

        logger.info(f"Adding volume to Kapowarr with data: {volume_data}")
        try:
            # Make a copy of volume_data to avoid modifying the original
            formatted_data = volume_data.copy()
            
            # Ensure comicvine_id is not None and is properly formatted
            if formatted_data.get("comicvine_id") is None:
                raise ValueError("comicvine_id cannot be None")
                
            # If root_folder_id is a string, convert to int
            if isinstance(formatted_data.get("root_folder_id"), str):
                try:
                    formatted_data["root_folder_id"] = int(formatted_data["root_folder_id"])
                except ValueError:
                    logger.warning(f"Could not convert root_folder_id '{formatted_data['root_folder_id']}' to integer")
            
            # Boolean values should be actual Python booleans
            for key in ['monitor', 'monitor_new_issues', 'auto_search']:
                if key in formatted_data and isinstance(formatted_data[key], str):
                    if formatted_data[key].lower() == 'true':
                        formatted_data[key] = True
                    elif formatted_data[key].lower() == 'false':
                        formatted_data[key] = False
            
            logger.debug(f"Sending formatted volume data to Kapowarr: {formatted_data}")
            response = self._make_request("POST", "volumes", json_data=formatted_data)
            return response.get("result", {})
        except Exception as e:
            # Check if there's an error message in the response
            error_message = str(e)
            error_type = None
            
            if hasattr(e, 'response') and e.response:
                try:
                    error_text = e.response.text
                    logger.debug(f"Full error response: {error_text}")
                    try:
                        error_json = e.response.json()
                        if 'error' in error_json:
                            error_message = f"{error_message} - API error: {error_json['error']}"
                            # Check if this is a VolumeAlreadyAdded error
                            if "VolumeAlreadyAdded" in error_json['error']:
                                error_type = "VolumeAlreadyAdded"
                    except Exception:
                        error_message = f"{error_message} - Response text: {error_text}"
                        # Check if this is a VolumeAlreadyAdded error from the text
                        if "VolumeAlreadyAdded" in error_text:
                            error_type = "VolumeAlreadyAdded"
                except Exception:
                    pass
            
            # Special handling for VolumeAlreadyAdded error
            if error_type == "VolumeAlreadyAdded" or "VolumeAlreadyAdded" in error_message:
                logger.info(f"Volume already exists in Kapowarr (ComicVine ID: {volume_data.get('comicvine_id')})")
                return {"error": "VolumeAlreadyAdded", "message": error_message}
            
            logger.error(f"Failed to add volume to Kapowarr: {error_message}")
            raise
    
    def get_volumes(self) -> List[Dict]:
        """
        Get all volumes from Kapowarr.
        """
        response = self._make_request("GET", "volumes")
        return response.get("result", [])

    def get_volume(self, volume_id: int) -> Dict:
        """
        Get a specific volume from Kapowarr.
        """
        response = self._make_request("GET", f"volumes/{volume_id}")
        return response.get("result", {})
        
    def refresh_and_scan_volume(self, volume_id: int) -> Dict:
        """
        Run a refresh and scan task for a specific volume in Kapowarr.
        This will make Kapowarr detect any newly copied files.
        """
        logger.info(f"Triggering refresh and scan for volume ID {volume_id}")
        
        # Create a task for refresh_and_scan
        task_data = {
            "cmd": "refresh_and_scan",
            "volume_id": volume_id
        }
        
        try:
            response = self._make_request("POST", "system/tasks", json_data=task_data)
            task_id = response.get("result", {}).get("id")
            if task_id:
                logger.info(f"Successfully created refresh and scan task (ID: {task_id}) for volume ID {volume_id}")
            else:
                logger.warning(f"Failed to get task ID for refresh and scan of volume ID {volume_id}")
            return response.get("result", {})
        except Exception as e:
            logger.error(f"Failed to create refresh and scan task for volume ID {volume_id}: {e}")
            return {}
            
    def mass_rename_issue(self, volume_id: int, issue_id: Optional[int] = None) -> Dict:
        """
        Run a mass rename task for a specific volume or issue in Kapowarr.
        This will rename files according to Kapowarr's file naming pattern.
        
        Args:
            volume_id: The ID of the volume to rename files for
            issue_id: Optional issue ID to rename files only for a specific issue
        
        Returns:
            Response from the Kapowarr API
        """
        task_name = "mass_rename_issue" if issue_id else "mass_rename"
        target_name = f"issue ID {issue_id}" if issue_id else f"volume ID {volume_id}"
        
        logger.info(f"Triggering mass rename for {target_name}")
        
        # Create a task for mass_rename or mass_rename_issue
        task_data = {
            "cmd": task_name,
            "volume_id": volume_id
        }
        
        # Add issue_id if provided
        if issue_id:
            task_data["issue_id"] = issue_id
        
        try:
            response = self._make_request("POST", "system/tasks", json_data=task_data)
            task_id = response.get("result", {}).get("id")
            if task_id:
                logger.info(f"Successfully created mass rename task (ID: {task_id}) for {target_name}")
            else:
                logger.warning(f"Failed to get task ID for mass rename of {target_name}")
            return response.get("result", {})
        except Exception as e:
            logger.error(f"Failed to create mass rename task for {target_name}: {e}")
            return {}
    
    def propose_library_import(self, folder_filter: str = None) -> List[Dict]:
        """
        Use Kapowarr's library import function to scan for comic files.
        """
        params = {}
        if folder_filter:
            params["folder_filter"] = folder_filter
        
        response = self._make_request("GET", "libraryimport", params=params)
        return response.get("result", [])
    
    def import_library(self, import_data: List[Dict], rename_files: bool = False) -> Dict:
        """
        Import comic files into Kapowarr.
        """
        params = {"rename_files": "true" if rename_files else "false"}
        response = self._make_request("POST", "libraryimport", params=params, json_data=import_data)
        return response.get("result", {})




def map_kapowarr_to_mylar_path(kapowarr_path: str, mylar_root: str, kapowarr_root: str) -> str:
    """
    Map Kapowarr's folder structure to Mylar's folder structure.
    
    Args:
        kapowarr_path: The path in Kapowarr (e.g., /comics-1/Marvel/Comic Name/Volume 01 (2022))
        mylar_root: The root path for Mylar files on the host system
        kapowarr_root: The root path for Kapowarr files on the host system
        
    Returns:
        The equivalent path in Mylar's filesystem
    """
    # First, convert from Kapowarr container path to a standard path
    if kapowarr_path.startswith("/comics-1/"):
        path = kapowarr_path[len("/comics-1/"):]
    else:
        path = kapowarr_path
    
    # Extract components: publisher/series/volume
    parts = path.strip('/').split('/')
    
    if len(parts) >= 1:
        publisher = parts[0]
        mylar_path = os.path.join(mylar_root, publisher)
        
        if len(parts) >= 2:
            series = parts[1]
            mylar_path = os.path.join(mylar_path, series)
            
            # If there's a volume component, add it
            if len(parts) >= 3:
                volume = parts[2]
                mylar_path = os.path.join(mylar_path, volume)
    else:
        # If we can't parse the path, just return the mylar root
        mylar_path = mylar_root
    
    logger.info(f"Mapped Kapowarr path {kapowarr_path} to Mylar path {mylar_path}")
    return mylar_path


def convert_path_to_kapowarr(mylar_path: str, mylar_root: str, kapowarr_root: str) -> str:
    """
    Convert a file path from Mylar format to Kapowarr format based on volume mapping.
    
    Args:
        mylar_path: The path in Mylar's format
        mylar_root: The root path in the host system for Mylar (/mnt/user/data/media/comics)
        kapowarr_root: The root path in the host system for Kapowarr (/mnt/user/data/media/kapowarr)
        
    Returns:
        The equivalent path in Kapowarr's format
    """
    # Handle docker volume mappings
    # Mylar container: /mnt/user/data/media/comics → /comics
    # Kapowarr container: /mnt/user/data/media/kapowarr → /comics-1
    
    # First, convert from Mylar container path to host path
    if mylar_path.startswith("/comics/"):
        host_path = mylar_path.replace("/comics/", f"{mylar_root}/")
    else:
        host_path = mylar_path
    
    # Then convert from host path to Kapowarr container path
    if host_path.startswith(mylar_root):
        kapowarr_path = host_path.replace(mylar_root, kapowarr_root)
    else:
        # If it's already using the host path pattern for Kapowarr
        if host_path.startswith(kapowarr_root):
            kapowarr_path = host_path
        else:
            # If we can't map it directly, just use the original path
            kapowarr_path = host_path
    
    return kapowarr_path


def copy_files_to_kapowarr(
    mylar_files: List[Dict], 
    kapowarr_volume: Dict,
    mylar_root: str, 
    kapowarr_root: str, 
    dry_run: bool = False,
    use_kapowarr_import: bool = False,
    kapowarr_api: Optional[Any] = None
) -> int:
    """
    Copy files from Mylar to Kapowarr's folder structure.
    
    Args:
        mylar_files: List of file information from Mylar
        kapowarr_volume: Volume information from Kapowarr
        mylar_root: The root path for Mylar files on the host system
        kapowarr_root: The root path for Kapowarr files on the host system
        dry_run: If True, don't actually copy files, just log what would be done
        use_kapowarr_import: If True, use Kapowarr's library import endpoint to import files
        kapowarr_api: The KapowarrAPI instance (required if use_kapowarr_import is True)
        
    Returns:
        Number of files successfully copied
    """
    if not mylar_files:
        return 0
    
    # Get volume info from Kapowarr
    volume_id = kapowarr_volume.get("id")
    volume_folder = kapowarr_volume.get("folder", "")
    if not volume_folder:
        logger.warning(f"Volume folder not specified for Kapowarr volume {volume_id}")
        return 0
    
    # Log the number of files we're processing
    logger.info(f"Processing {len(mylar_files)} files for volume ID {volume_id}")
    for i, file_info in enumerate(mylar_files):
        issue_number = file_info.get("issue_number", "unknown")
        file_path = file_info.get("file_path", "unknown")
        logger.info(f"File {i+1}/{len(mylar_files)}: Issue #{issue_number}, Path: {file_path}")
    
    # If using Kapowarr import, prepare import data for API
    if use_kapowarr_import and kapowarr_api:
        if dry_run:
            logger.info("DRY RUN: Would import files using Kapowarr's library import API")
            for file_info in mylar_files:
                source_path = file_info["file_path"]
                if source_path.startswith("/comics/"):
                    source_host_path = source_path.replace("/comics/", f"{mylar_root}/")
                else:
                    source_host_path = source_path
                logger.info(f"DRY RUN: Would prepare file for import: {source_host_path}")
            return len(mylar_files)
        
        # Prepare import data - we'll need file paths and issue IDs
        import_data = []
        for file_info in mylar_files:
            source_path = file_info["file_path"]
            # Convert container path to host path if needed
            if source_path.startswith("/comics/"):
                source_host_path = source_path.replace("/comics/", f"{mylar_root}/")
            else:
                source_host_path = source_path
            
            if not os.path.isfile(source_host_path):
                logger.warning(f"Source file does not exist: {source_host_path}")
                continue
            
            # Convert to Kapowarr container path for import
            kapowarr_path = source_host_path.replace(mylar_root, "/comics-1")
            
            # Find issue ID from Kapowarr volume data
            issue_id = None
            issue_number = file_info.get("issue_number", "")
            if issue_number and "issues" in kapowarr_volume:
                for issue in kapowarr_volume["issues"]:
                    if str(issue.get("issue_number", "")) == str(issue_number):
                        issue_id = issue.get("id")
                        break
            
            if issue_id:
                import_data.append({
                    "filepath": kapowarr_path,
                    "id": issue_id
                })
                logger.info(f"Prepared file for import: {kapowarr_path} -> Issue ID: {issue_id}")
            else:
                logger.warning(f"Could not find issue ID for file: {source_host_path} (issue #{issue_number})")
                # Add it anyway with volume ID for now
                import_data.append({
                    "filepath": kapowarr_path,
                    "id": volume_id
                })
                logger.info(f"Added file to import with volume ID: {kapowarr_path} -> Volume ID: {volume_id}")
        
        # Import the files using Kapowarr's API
        if import_data:
            try:
                logger.info(f"Importing {len(import_data)} files using Kapowarr's library import API")
                result = kapowarr_api.import_library(import_data, rename_files=True)
                logger.info(f"Import result: {result}")
                return len(import_data)
            except Exception as e:
                logger.error(f"Error importing files using Kapowarr API: {e}")
                return 0
        else:
            logger.warning("No files prepared for import")
            return 0
    
    # Using direct file copy method
    # Make sure the folder starts with the Kapowarr container path
    if not volume_folder.startswith("/comics-1/"):
        volume_folder = os.path.join("/comics-1", volume_folder)
    
    # Convert to host path for file operations
    host_volume_folder = volume_folder.replace("/comics-1/", f"{kapowarr_root}/")
    
    # Create the destination folder if it doesn't exist
    os.makedirs(host_volume_folder, exist_ok=True)
    
    copied_count = 0
    
    for file_info in mylar_files:
        source_path = file_info["file_path"]
        
        # Convert container path to host path if needed
        if source_path.startswith("/comics/"):
            source_host_path = source_path.replace("/comics/", f"{mylar_root}/")
        else:
            source_host_path = source_path
        
        # Additional check: some paths might be absolute but not in container format
        if not os.path.isfile(source_host_path) and not source_host_path.startswith(mylar_root):
            # Try to interpret it as a relative path within the mylar root
            alternative_path = os.path.join(mylar_root, source_host_path.lstrip('/'))
            if os.path.isfile(alternative_path):
                logger.info(f"Found file at alternative path: {alternative_path}")
                source_host_path = alternative_path
        
        if not os.path.isfile(source_host_path):
            logger.warning(f"Source file does not exist: {source_host_path}")
            continue
        
        # Get the filename and create the destination path
        filename = os.path.basename(source_path)
        dest_host_path = os.path.join(host_volume_folder, filename)
        
        # Enhance the destination filename with issue number if available
        issue_number = file_info.get("issue_number", "")
        if issue_number and not re.search(rf'#\s*{issue_number}', filename):
            base, ext = os.path.splitext(filename)
            dest_filename = f"{base} #{issue_number.zfill(3)}{ext}"
            dest_host_path = os.path.join(host_volume_folder, dest_filename)
            logger.info(f"Enhanced destination filename with issue number: {dest_filename}")
        
        if os.path.exists(dest_host_path):
            logger.info(f"File already exists at destination: {dest_host_path}")
            copied_count += 1
            continue
        
        try:
            if not dry_run:
                logger.info(f"Copying from {source_host_path} to {dest_host_path}")
                shutil.copy2(source_host_path, dest_host_path)
                # Set appropriate permissions
                os.chmod(dest_host_path, 0o644)  # rw-r--r--
                copied_count += 1
            else:
                logger.info(f"DRY RUN: Would copy from {source_host_path} to {dest_host_path}")
                copied_count += 1
        except Exception as e:
            logger.error(f"Error copying file {source_host_path} to {dest_host_path}: {e}")
    
    return copied_count


def migrate_comics(
    mylar_url: str, 
    mylar_api_key: str, 
    kapowarr_url: str,
    kapowarr_api_key: str, 
    root_folder_id: int, 
    kapowarr_root: str,
    copy_files: bool,
    dry_run: bool,
    limit: int, 
    resume_from: str = None,
    rename_files: bool = False,
    refresh_scan: bool = False,
    mass_rename: bool = False,
    delay: int = 20
):
    """
    Migrate comics from Mylar to Kapowarr.
    """
    mylar = MylarAPI(mylar_url, mylar_api_key)
    kapowarr = KapowarrAPI(kapowarr_url, kapowarr_api_key)
    
    # Get list of comics from Mylar using getIndex command
    try:
        comics = mylar.get_comics(cmd="getIndex")
    except Exception as e:
        logger.error(f"Failed to retrieve comics from Mylar: {e}")
        return
    
    logger.info(f"Found {len(comics)} comics in Mylar")
    
    # Get wanted issues for monitoring
    wanted_issues_data = mylar.get_wanted()
    wanted_issues = set()
    
    # Process issues
    for issue in wanted_issues_data.get("issues", []):
        issue_id = issue.get("IssueID")
        if issue_id:
            wanted_issues.add(issue_id)
    
    # Process annuals
    for annual in wanted_issues_data.get("annuals", []):
        issue_id = annual.get("IssueID")
        if issue_id:
            wanted_issues.add(issue_id)
    
    logger.info(f"Found {len(wanted_issues)} wanted issues in Mylar")
    
    # Apply limit if specified
    if limit and limit > 0:
        comics = comics[:limit]
        logger.info(f"Limiting migration to first {limit} comics")
    
    # If resuming, skip until we find the comic to resume from
    if resume_from:
        resume_from = resume_from.lower()
        resume_index = None
        
        for i, comic in enumerate(comics):
            if comic.get("name", "").lower() == resume_from:
                resume_index = i
                break
        
        if resume_index is not None:
            comics = comics[resume_index:]
            logger.info(f"Resuming migration from {resume_from} ({len(comics)} comics remaining)")
        else:
            logger.warning(f"Could not find comic '{resume_from}' to resume from")
    
    # Process each comic from Mylar's response
    for idx, comic in enumerate(comics, start=1):
        # Extract data based on command format
        title = comic.get("name") or comic.get("ComicName") or comic.get("Title") or "Unknown Title"
        comicvine_id = comic.get("id") or comic.get("ComicID") or comic.get("comicid")
        
        if not comicvine_id:
            logger.warning(f"Skipping comic '{title}' as it has no ComicVine ID")
            continue
            
        # For this example, we assume that if the comic's status is "Active", we want to monitor it.
        status = comic.get("status") or comic.get("Status") or ""
        if isinstance(status, str):
            status = status.lower()
        monitored = status == "active"
        
        logger.info(f"[{idx}/{len(comics)}] {title}")
        
        # Check if this comic is already added to Kapowarr
        if kapowarr.is_volume_added(comicvine_id):
            logger.info(f"✓ Already in Kapowarr")
            continue
        
        # Prepare the payload for adding a new volume
        # Kapowarr might expect numeric IDs for comicvine_id
        # Try to remove any non-numeric prefix (like "4050-")
        cv_id = str(comicvine_id)
        if '-' in cv_id:
            cv_id = cv_id.split('-')[-1]
        
        # Keep it simple - only include required fields
        volume_data = {
            "comicvine_id": cv_id,
            "root_folder_id": int(root_folder_id)
        }
        
        # Only add optional fields if they need non-default values
        if not monitored:  # Default is True
            volume_data["monitor"] = False
            volume_data["monitor_new_issues"] = False
        
        try:
            # Add the volume to Kapowarr
            kap_result = kapowarr.add_volume(volume_data)
            
            # Check for VolumeAlreadyAdded error
            if isinstance(kap_result, dict) and kap_result.get("error") == "VolumeAlreadyAdded":
                logger.info(f"✓ Already in Kapowarr")
                continue
            
            # Normal successful add
            kap_volume_id = kap_result.get("id")
            
            if not kap_volume_id:
                logger.error(f"Failed to get volume ID after adding {title} to Kapowarr")
                continue
                
            logger.info(f"✓ Added to Kapowarr (ID: {kap_volume_id})")
            
            # Get volume details to get folder path
            kap_volume = kapowarr.get_volume(kap_volume_id)
            
            # If copy_files is enabled, download files from Mylar API directly
            if copy_files:
                # Get issues from Kapowarr
                issues = kap_volume.get("issues", [])
                if not issues:
                    logger.warning(f"No issues found in Kapowarr")
                else:
                    logger.info(f"Found {len(issues)} issues in Kapowarr")
                    
                    # Get corresponding issues from Mylar
                    mylar_issues = []
                    comic_info = mylar.get_comic_info(comicvine_id)
                    if comic_info and "issues" in comic_info:
                        mylar_issues = comic_info.get("issues", [])
                        logger.info(f"Found {len(mylar_issues)} issues in Mylar")
                    else:
                        logger.warning(f"No issues found in Mylar")
                    
                    # Get volume destination path
                    kapowarr_folder = kap_volume.get("folder", "")
                    if not kapowarr_folder:
                        logger.warning(f"No folder specified in Kapowarr")
                        continue
                        
                    # Convert to host path
                    if kapowarr_folder.startswith("/comics-1/"):
                        host_folder = kapowarr_folder.replace("/comics-1/", f"{kapowarr_root}/")
                    else:
                        host_folder = os.path.join(kapowarr_root, kapowarr_folder.lstrip("/"))
                    
                    # Make sure the destination directory exists
                    os.makedirs(host_folder, exist_ok=True)
                    
                    # Count successful downloads
                    download_count = 0
                    
                    # Process each issue from Kapowarr
                    for issue in issues:
                        # Get issue number from Kapowarr
                        issue_number = issue.get("issue_number", "")
                        
                        # Try to match by issue number with Mylar issues
                        matched = False
                        for mylar_issue in mylar_issues:
                            # Try different possible field names for issue number
                            mylar_issue_num = (
                                mylar_issue.get("issue_number", "") or 
                                mylar_issue.get("Issue_Number", "") or 
                                mylar_issue.get("IssueNumber", "") or
                                mylar_issue.get("number", "")
                            )
                            if str(mylar_issue_num) == str(issue_number):
                                # Found matching issue by number
                                # Get the issue ID - this is different from the comic ID
                                mylar_issue_id = mylar_issue.get("id")  # In getComic response, it's just "id"
                                if mylar_issue_id:
                                    matched = True
                                    logger.info(f"  ✓ Issue #{issue_number} (ID: {mylar_issue_id})")
                                    
                                    if not dry_run:
                                        # Download the issue from Mylar using the downloadIssue endpoint
                                        url = f"{mylar_url}/api"
                                        params = {
                                            "apikey": mylar_api_key,
                                            "cmd": "downloadIssue",
                                            "id": mylar_issue_id  # This should be the issue ID, not the comic ID
                                        }
                                        
                                        try:
                                            response = requests.get(url, params=params, stream=True)
                                            response.raise_for_status()
                                            
                                            # Get filename from Content-Disposition header
                                            filename = None
                                            if 'Content-Disposition' in response.headers:
                                                content_disposition = response.headers['Content-Disposition']
                                                filename_match = re.search(r'filename="([^"]+)"', content_disposition)
                                                if filename_match:
                                                    filename = filename_match.group(1)
                                            
                                            if not filename:
                                                filename = f"issue_{mylar_issue_id}.cbz"
                                                logger.info(f"    ⚠ Skipping placeholder file (not yet released/downloaded)")
                                                continue
                                            
                                            file_path = os.path.join(host_folder, filename)
                                            
                                            with open(file_path, 'wb') as f:
                                                for chunk in response.iter_content(chunk_size=8192):
                                                    if chunk:
                                                        f.write(chunk)
                                            
                                            logger.info(f"    ✓ Downloaded to {file_path}")
                                            download_count += 1
                                        except Exception as e:
                                            logger.error(f"    ✗ Failed to download: {e}")
                                    else:
                                        logger.info(f"    ✓ Would download")
                                        download_count += 1
                                    break
                        
                        if not matched:
                            logger.warning(f"  ✗ No matching Mylar issue found for issue #{issue_number}")
                    
                    logger.info(f"  Downloaded {download_count} files")
                    
                    # If refresh_scan is enabled, trigger a refresh and scan task
                    if refresh_scan and not dry_run and download_count > 0:
                        logger.info(f"  ✓ Triggering refresh and scan")
                        kapowarr.refresh_and_scan_volume(kap_volume_id)
                        
                    # If mass_rename is enabled, trigger a mass rename task
                    if mass_rename and not dry_run and download_count > 0:
                        logger.info(f"  ✓ Triggering mass rename")
                        kapowarr.mass_rename_issue(kap_volume_id)
            
        except Exception as e:
            logger.error(f"✗ Failed to process: {e}")
        
        # Sleep to respect ComicVine API rate limits
        if delay > 0:
            logger.info(f"Sleeping for {delay} seconds...")
            time.sleep(delay)
        else:
            logger.warning("No delay between comics - this may hit ComicVine API rate limits")
    
    logger.info("Migration complete.")


def test_mylar_api(url: str, api_key: str, cmd: str):
    """
    Test the Mylar API with a specific command.
    
    Args:
        url: The Mylar API URL
        api_key: The Mylar API key
        cmd: The command to test (e.g., 'getComics', 'getIndex', 'getComic')
    """
    logger.info(f"Testing Mylar API with command: {cmd}")
    
    mylar = MylarAPI(url, api_key)
    params = {}
    
    # Add ID parameter for commands that require it
    if cmd in ["getComic"]:
        # This is a placeholder - for actual testing you'd need a valid comic ID
        params["id"] = 1  
    
    # Make the API request
    mylar._make_request(cmd, params)
    
    logger.info(f"Mylar API test with {cmd} completed")


def find_comics_with_files(mylar_url: str, mylar_api_key: str, limit: int = 5) -> List[Dict]:
    """
    Find comics in Mylar that have actual files associated with them.
    
    Args:
        mylar_url: The base URL for Mylar
        mylar_api_key: The API key for Mylar
        limit: Maximum number of comics to check
        
    Returns:
        List of comics with files
    """
    mylar = MylarAPI(mylar_url, mylar_api_key)
    comics = mylar.get_comics(cmd="getIndex")
    
    logger.info(f"Checking up to {limit} comics for files")
    comics_with_files = []
    
    for i, comic in enumerate(comics[:limit]):
        comic_id = comic.get("id") or comic.get("ComicID") or comic.get("comicid")
        title = comic.get("name") or comic.get("ComicName") or comic.get("Title") or "Unknown"
        
        if not comic_id:
            continue
            
        logger.info(f"Checking if comic '{title}' (ID: {comic_id}) has files")
        
        files = get_mylar_comic_files(mylar_url, mylar_api_key, comic_id, title)
        
        if files:
            logger.info(f"Comic '{title}' has {len(files)} files")
            comics_with_files.append({
                "id": comic_id,
                "title": title,
                "files": files
            })
        else:
            logger.info(f"Comic '{title}' has no files")
    
    logger.info(f"Found {len(comics_with_files)} comics with files")
    return comics_with_files


def test_kapowarr_api(url: str, api_key: str, test_type: str = "auth"):
    """
    Test the Kapowarr API.
    
    Args:
        url: The Kapowarr API URL
        api_key: The Kapowarr API key
        test_type: The type of test to perform ("auth", "root_folders", "add_volume")
    """
    logger.info(f"Testing Kapowarr API with test type: {test_type}")
    
    kapowarr = KapowarrAPI(url, api_key)
    
    if test_type == "auth":
        # Already authenticated in constructor
        logger.info("Authentication test completed successfully")
    
    elif test_type == "root_folders":
        # Test getting root folders
        root_folders = kapowarr.get_root_folders()
        logger.info(f"Root folders: {root_folders}")
    
    elif test_type == "add_volume":
        # Test adding a volume with minimal data - only required fields
        test_data = {
            "comicvine_id": "145299",  # A.X.E.: Avengers
            "root_folder_id": 2  # ID 2 is /comics-1/, ID 1 is /temp-comics/
        }
        try:
            logger.info(f"Testing add_volume with data: {test_data}")
            result = kapowarr.add_volume(test_data)
            logger.info(f"Add volume result: {result}")
        except Exception as e:
            logger.error(f"Add volume test failed: {e}")
    
    logger.info(f"Kapowarr API test with {test_type} completed")


def load_config(config_path: str = "config.json") -> dict:
    """
    Load configuration from config.json file.
    
    Args:
        config_path: Path to the config file
        
    Returns:
        Dictionary containing the configuration
    """
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except FileNotFoundError:
        logger.warning(f"Config file {config_path} not found, using default values")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing config file {config_path}: {e}")
        return {}

def main():
    # Load default configuration
    config = load_config()
    
    parser = argparse.ArgumentParser(description="Migrate comics from Mylar to Kapowarr")
    
    # Create required arguments groups - we can't use required=True with conditional logic
    required_args = parser.add_argument_group('required arguments')
    kapowarr_args = parser.add_argument_group('kapowarr arguments')
    mylar_args = parser.add_argument_group('mylar arguments')
    
    # Kapowarr parameters - always required
    kapowarr_args.add_argument("--kapowarr-url", 
                              default=config.get("kapowarr", {}).get("url"),
                              help="Base URL for Kapowarr (e.g., http://192.168.2.2:5656)")
    kapowarr_args.add_argument("--kapowarr-api-key", 
                              default=config.get("kapowarr", {}).get("api_key"),
                              help="API key for Kapowarr")
    
    # Mylar parameters - only required for migration, not for Kapowarr-only testing
    mylar_args.add_argument("--mylar-url", 
                           default=config.get("mylar", {}).get("url"),
                           help="Base URL for Mylar (e.g., http://192.168.2.2:8090)")
    mylar_args.add_argument("--mylar-api-key", 
                           default=config.get("mylar", {}).get("api_key"),
                           help="API key for Mylar")
    
    # Root folder - only needed for migration or adding volumes
    parser.add_argument("--root-folder-id", 
                       type=int,
                       default=config.get("kapowarr", {}).get("root_folder_id"),
                       help="Kapowarr root folder ID (e.g., 2)")
    
    # File copying options
    parser.add_argument("--kapowarr-root", 
                       default=config.get("kapowarr", {}).get("root", "/mnt/user/data/media/kapowarr"), 
                       help="The root path for Kapowarr files on the host system")
    parser.add_argument("--copy-files", 
                       action="store_true",
                       default=config.get("options", {}).get("copy_files", False),
                       help="Copy files from Mylar to Kapowarr")
    parser.add_argument("--rename-files", 
                       action="store_true",
                       default=config.get("options", {}).get("rename_files", False),
                       help="Use Kapowarr's library import API to rename files according to Kapowarr's naming scheme")
    parser.add_argument("--refresh-scan", 
                       action="store_true",
                       default=config.get("options", {}).get("refresh_scan", False),
                       help="Trigger a refresh and scan task in Kapowarr after copying files")
    parser.add_argument("--mass-rename", 
                       action="store_true",
                       default=config.get("options", {}).get("mass_rename", False),
                       help="Trigger a mass rename task in Kapowarr after copying files")
    parser.add_argument("--dry-run", 
                       action="store_true",
                       default=config.get("options", {}).get("dry_run", False),
                       help="Don't actually copy files, just log what would be done")
    
    # Mylar API options
    parser.add_argument("--test-mylar", action="store_true", 
                       help="Test the Mylar API with various commands")
    parser.add_argument("--test-cmd", default="getIndex", 
                       help="Command to test when using --test-mylar (default: getIndex)")
    
    # Kapowarr API options
    parser.add_argument("--test-kapowarr", action="store_true",
                       help="Test the Kapowarr API")
    parser.add_argument("--test-kapowarr-type", default="auth",
                       choices=["auth", "root_folders", "add_volume"],
                       help="Type of Kapowarr API test to perform (default: auth)")
                       
    # Search options
    parser.add_argument("--find-comics-with-files", action="store_true",
                       help="Find comics in Mylar that have actual files associated with them")
    parser.add_argument("--search-limit", type=int, default=5,
                       help="Maximum number of comics to check when searching for files (default: 5)")
    
    # Limiting options
    parser.add_argument("--limit", 
                       type=int, 
                       default=config.get("options", {}).get("limit", 0),
                       help="Limit the number of comics to migrate (for testing)")
    parser.add_argument("--resume-from", type=str, help="Resume migration from this comic title")
    parser.add_argument("--delay", 
                       type=int, 
                       default=config.get("options", {}).get("delay", 20),
                       help="Delay between comics in seconds to respect ComicVine API rate limits")
    
    # Logging options
    parser.add_argument("--log-level", 
                       default=config.get("options", {}).get("log_level", "INFO"),
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="Set the logging level")
    
    args = parser.parse_args()
    
    logger.setLevel(args.log_level)
    
    # Test Mylar API if requested
    if args.test_mylar:
        if not args.mylar_url or not args.mylar_api_key:
            parser.error("--mylar-url and --mylar-api-key are required for --test-mylar")
        test_mylar_api(args.mylar_url, args.mylar_api_key, args.test_cmd)
    
    # Test Kapowarr API if requested
    elif args.test_kapowarr:
        test_kapowarr_api(args.kapowarr_url, args.kapowarr_api_key, args.test_kapowarr_type)
    
    # Find comics with files if requested
    elif args.find_comics_with_files:
        if not args.mylar_url or not args.mylar_api_key:
            parser.error("--mylar-url and --mylar-api-key are required for --find-comics-with-files")
        
        comics_with_files = find_comics_with_files(args.mylar_url, args.mylar_api_key, args.search_limit)
        
        if comics_with_files:
            logger.info("Comics with files:")
            for comic in comics_with_files:
                logger.info(f"- {comic['title']} (ID: {comic['id']}) has {len(comic['files'])} files")
                for i, file_info in enumerate(comic['files']):
                    logger.info(f"  - File {i+1}: {file_info['file_path']}")
        else:
            logger.info("No comics with files found")
    
    # Migration
    else:
        # Check required arguments for migration
        if not args.mylar_url or not args.mylar_api_key:
            parser.error("--mylar-url and --mylar-api-key are required for migration")
        
        if not args.root_folder_id:
            parser.error("--root-folder-id is required for migration")
            
        migrate_comics(
            args.mylar_url,
            args.mylar_api_key,
            args.kapowarr_url,
            args.kapowarr_api_key,
            args.root_folder_id,
            args.kapowarr_root,
            args.copy_files,
            args.dry_run,
            args.limit,
            args.resume_from,
            args.rename_files,
            args.refresh_scan,
            args.mass_rename,
            args.delay
        )


if __name__ == "__main__":
    main()
