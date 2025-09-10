import google_drive as gd
import logging

# Configure basic logging to see the steps.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def find_folders_in_parent(parent_folder_name: str):
    """
    Finds and lists all direct child folders within a specified parent folder.
    """
    try:
        # 1. Authenticate with Google Drive.
        logging.info("Authenticating with Google Drive...")
        drive_service = gd.get_drive_service()
        logging.info("Authentication successful.")

        # 2. Find the parent folder to get its ID.
        logging.info(f"Searching for the parent folder: '{parent_folder_name}'")
        parent_query = f"name = '{parent_folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
        parent_folders = gd.find_files(drive_service, parent_query)

        if not parent_folders:
            print(f"\nCould not find the parent folder named '{parent_folder_name}'. Please check the name and try again.")
            return

        # Assuming the first result is the correct one.
        parent_folder = parent_folders[0]
        parent_folder_id = parent_folder['id']
        logging.info(f"Found parent folder with ID: {parent_folder_id}")

        # 3. Find all folders that are direct children of the parent folder.
        child_query = f"'{parent_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder'"
        logging.info(f"Searching for child folders with query: '{child_query}'")
        child_folders = gd.find_files(drive_service, child_query)

        # 4. Print the results.
        if not child_folders:
            print(f"\nNo child folders were found directly inside '{parent_folder_name}'.")
        else:
            print(f"\nFound {len(child_folders)} child folders in '{parent_folder_name}':")
            print("-" * 70)
            for folder in child_folders:
                print(f"  - Name: {folder['name']:<40} | ID: {folder['id']}")
            print("-" * 70)

    except FileNotFoundError as e:
        logging.error(f"ERROR: Credential file not found. {e}")
        print("\nERROR: Could not find 'credential.json'. Please ensure the file is in the correct location.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    # The name of the parent folder you want to search inside.
    TARGET_PARENT_FOLDER = "_0.ปิดงบการเงินปี2568_2025"
    find_folders_in_parent(TARGET_PARENT_FOLDER)
