import google_drive as gd
import logging

# Configure basic logging to see the steps.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def find_all_shared_folders():
    """
    Finds and lists all folders shared with the configured Google Drive service account.
    """
    try:
        # 1. Authenticate with Google Drive using your existing function.
        logging.info("Authenticating with Google Drive...")
        drive_service = gd.get_drive_service()
        logging.info("Authentication successful.")

        # 2. Define the query to find all folders.
        query = "mimeType = 'application/vnd.google-apps.folder'"
        logging.info(f"Searching for folders with query: '{query}'")

        # 3. Find the folders using your existing function.
        folders = gd.find_files(drive_service, query)

        # 4. Print the results in a clean format.
        if not folders:
            print("\nNo folders were found to be shared with the service account.")
        else:
            print(f"\nFound {len(folders)} folders shared with the service account:")
            print("-" * 70)
            for folder in folders:
                print(f"  - Name: {folder['name']:<40} | ID: {folder['id']}")
            print("-" * 70)

    except FileNotFoundError as e:
        logging.error(f"ERROR: Credential file not found. {e}")
        print("\nERROR: Could not find 'credential.json'. Please ensure the file is in the correct location.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    find_all_shared_folders()
