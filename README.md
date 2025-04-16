# Mylar to Kapowarr Migration Script

A Python script to migrate comic metadata and files from Mylar3 to Kapowarr. This script handles the transfer of comic series information, issue metadata, and actual comic files while maintaining proper organization in Kapowarr's folder structure.

## Features

- Migrates comic series metadata from Mylar to Kapowarr
- Downloads and transfers actual comic files
- Maintains proper folder structure in Kapowarr
- Skips placeholder files for unreleased issues
- Supports batch processing with configurable limits
- Configurable through `config.json` or command-line arguments
- Respects ComicVine API rate limits
- Supports dry-run mode for testing

## Prerequisites

- Python 3.x
- Mylar3 instance with API access
- Kapowarr instance with API access
- Access to both Mylar and Kapowarr file systems

## Installation

1. Clone this repository or download the script
2. Install required Python packages:
   ```bash
   pip install requests
   ```

## Configuration

Create a `config.json` file in the same directory as the script with the following structure:

```json
{
    "mylar": {
        "url": "http://your-mylar-url:port",
        "api_key": "your-mylar-api-key"
    },
    "kapowarr": {
        "url": "http://your-kapowarr-url:port",
        "api_key": "your-kapowarr-api-key",
        "root": "/path/to/kapowarr/root",
        "root_folder_id": 1
    },
    "options": {
        "copy_files": true,
        "refresh_scan": true,
        "mass_rename": true,
        "dry_run": false,
        "delay": 25,
        "log_level": "INFO",
        "limit": 0
    }
}
```

### Configuration Options

#### Mylar Settings
- `url`: Base URL of your Mylar instance
- `api_key`: Your Mylar API key

#### Kapowarr Settings
- `url`: Base URL of your Kapowarr instance
- `api_key`: Your Kapowarr API key
- `root`: Root directory for Kapowarr files on the host system (not the container path)
  - For Docker users: Use the host path that maps to Kapowarr's `/comics-1` directory
  - Example: If your Docker volume mapping is `/mnt/user/data/media/kapowarr:/comics-1`, use `/mnt/user/data/media/kapowarr`
- `root_folder_id`: ID of the root folder in Kapowarr (typically 1 for `/comics-1`)

#### Options
- `copy_files`: Whether to copy files from Mylar to Kapowarr
- `refresh_scan`: Whether to trigger a refresh and scan after copying files
- `mass_rename`: Whether to trigger Kapowarr's built-in mass rename task after copying files
  - This will rename files according to Kapowarr's naming scheme
  - Recommended to enable this for proper file organization
- `dry_run`: If true, only log what would be done without making changes
- `delay`: Delay between comics in seconds (to respect API rate limits)
  - Recommended minimum: 20 seconds
  - Default: 25 seconds
- `log_level`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `limit`: Maximum number of comics to process (0 for all)

## Usage

### Basic Usage

```bash
python mylar2kapowarr.py
```

This will use the settings from `config.json` to migrate comics from Mylar to Kapowarr.

### Command Line Arguments

All settings from `config.json` can be overridden using command-line arguments:

```bash
# Test Mylar API connection
python mylar2kapowarr.py --test-mylar

# Test Kapowarr API connection
python mylar2kapowarr.py --test-kapowarr

# Process a limited number of comics
python mylar2kapowarr.py --limit 5

# Resume from a specific comic
python mylar2kapowarr.py --resume-from "Comic Title"

# Dry run (no actual changes)
python mylar2kapowarr.py --dry-run

# Override API settings
python mylar2kapowarr.py --mylar-url "http://new-url:port" --mylar-api-key "new-key"
```

### Output

The script provides detailed logging of its operations:

```
Found 411 comics in Mylar
[1/411] Comic Title
✓ Already in Kapowarr
[2/411] Another Comic
✓ Added to Kapowarr (ID: 123)
Found 5 issues in Kapowarr
Found 5 issues in Mylar
  ✓ Issue #1 (ID: 456)
    ✓ Downloaded to /path/to/file.cbz
  ⚠ Skipping placeholder file (not yet released/downloaded)
  Downloaded 4 files
  ✓ Triggering refresh and scan
  ✓ Triggering mass rename
```

## Troubleshooting

### Common Issues

1. **API Connection Issues**
   - Verify your API URLs and keys
   - Check if both services are running and accessible
   - Use `--test-mylar` and `--test-kapowarr` to test connections

2. **File Permission Issues**
   - Ensure the script has write access to Kapowarr's root directory
   - Check file permissions on both Mylar and Kapowarr directories
   - For Docker users: Make sure the host path specified in `root` matches your Docker volume mapping

3. **Rate Limiting**
   - If you encounter API rate limits, increase the `delay` in config.json
   - Recommended minimum delay is 20 seconds between comics
   - Default is 25 seconds between comics
   - Increase the delay if you experience rate limiting issues

### Logging

- Use `--log-level DEBUG` for detailed logging
- Logs show the progress of each comic and file operation
- Errors are clearly marked with ✗
- Successes are marked with ✓
- Placeholder files are marked with ⚠

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Migration Process

The script performs the migration in the following steps:

1. **Comic Series Migration**
   - Fetches all comic series from Mylar
   - Adds each series to Kapowarr if it doesn't already exist
   - Maintains the same monitoring status as in Mylar

2. **Issue Processing**
   - For each comic series:
     - Fetches all issues from Mylar
     - Matches issues with Kapowarr
     - Skips placeholder files for unreleased issues

3. **File Transfer**
   - Downloads files directly from Mylar
   - Saves them to Kapowarr's folder structure
   - Maintains proper file organization

4. **Post-Processing**
   - If enabled, triggers a refresh and scan in Kapowarr
   - If enabled, runs Kapowarr's built-in mass rename task to ensure proper file naming
   - Respects API rate limits with configurable delays

### Example Flow

```
1. Fetch comics from Mylar
   └─ Found 411 comics

2. Process each comic
   ├─ Check if exists in Kapowarr
   │  ├─ If exists: Skip
   │  └─ If new: Add to Kapowarr
   │
   ├─ Get issues from Mylar
   │  └─ Found 5 issues
   │
   ├─ Match and download issues
   │  ├─ Issue #1: Download file
   │  ├─ Issue #2: Skip placeholder
   │  └─ Issue #3: Download file
   │
   └─ Post-process
      ├─ Refresh and scan
      └─ Mass rename
```

### Important Notes

- The script maintains the original ComicVine IDs to ensure proper metadata matching
- Files are downloaded directly from Mylar's API
- Placeholder files for unreleased issues are automatically skipped
- The script can be resumed from any point using the `--resume-from` option
- Rate limiting is built-in to prevent API throttling

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the LICENSE file for details. 
