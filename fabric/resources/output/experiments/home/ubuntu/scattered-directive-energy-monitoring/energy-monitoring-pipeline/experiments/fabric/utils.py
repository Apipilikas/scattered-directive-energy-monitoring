import os
import sys
import shutil
import datetime

def zip_directories_with_prefix(prefix):
    current_dir = os.getcwd()
    
    # Find all directories in the current folder matching the prefix
    matching_folders = [
        f for f in os.listdir(current_dir) 
        if os.path.isdir(os.path.join(current_dir, f)) and f.startswith(prefix)
    ]

    if not matching_folders:
        print(f">!< ERROR: No folders found starting with prefix: '{prefix}'")
        return

    print(f"> Found {len(matching_folders)} matching folders:")
    for folder in matching_folders:
        print(f"    - {folder}")

    archive_name = f"{prefix}_archive"
    temp_dir = f"_temp_{archive_name}"

    try:
        print(f"\n> Bundling into {archive_name}.zip...")
        os.makedirs(temp_dir, exist_ok=True)

        for folder in matching_folders:
            shutil.copytree(folder, os.path.join(temp_dir, folder))

        shutil.make_archive(archive_name, 'zip', temp_dir)
        print(f"> Success! Created archive: {archive_name}.zip")

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def clean_current_directory(keep_prefixes = None):
    cwd = os.getcwd()
    print(f"> Deleting all sub-folders inside:\n    {cwd}")
    count = 0
    for item in os.listdir(cwd):
        if keep_prefixes is not None and item.startswith(tuple(keep_prefixes)):
            print(f"> Skipping directory {item}.")
            continue
            
        p = os.path.join(cwd, item)
        
        if os.path.isdir(p) and not item.startswith('.'):
            try:
                shutil.rmtree(p)
                count += 1
            except Exception as e:
                print(f">!< Failed on {item}: {e}")

    print(f"> Done. Successfully deleted {count} files.")