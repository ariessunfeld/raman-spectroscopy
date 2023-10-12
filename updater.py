import requests
import os
from shutil import unpack_archive

# Constants
MANIFEST_URL = "https://github.com/ariessunfeld/raman-spectroscopy/blob/main/manifest.json"
CURRENT_VERSION_FILE = "version.txt"

def get_remote_version():
    response = requests.get(MANIFEST_URL)
    data = response.json()
    return data['version'], data['download_url']

def get_local_version():
    with open(CURRENT_VERSION_FILE, 'r') as file:
        return file.read().strip()

def update_version(version):
    with open(CURRENT_VERSION_FILE, 'w') as file:
        file.write(version)

def main():
    local_version = get_local_version()
    remote_version, download_url = get_remote_version()
    
    if local_version != remote_version:
        print(f"New version {remote_version} is available. You have {local_version}.")
        choice = input("Do you want to update? [Y/N]: ").lower()
        
        if choice == 'y':
            # Download and extract new version
            response = requests.get(download_url, stream=True)
            with open("temp_update.zip", 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            unpack_archive("temp_update.zip", remote_version)
            os.remove("temp_update.zip")
            
            # Update the version locally
            update_version(remote_version)

if __name__ == "__main__":
    main()

