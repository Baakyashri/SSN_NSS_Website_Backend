import os
from db import db

def populate_albums():
    print("Populating albums with photos from assets folder...")

    albums_col = db['albums']

    # Clear existing albums and create new ones with proper names
    albums_col.drop()

    # Map folder names to proper album names
    folder_to_album = {
        'Camp Photos': 'Annual Camp 2025',
        'camp-gallery': 'Annual Camp Gallery',
        'NSS PHOTOGRPAHS/BEACH CLEANUP': 'Beach Cleanup Drive',
        'NSS PHOTOGRPAHS/BLOOD DONATION': 'Blood Donation Camp',
        'NSS PHOTOGRPAHS/TREE PLANATION AT HOME': 'Tree Plantation Drive',
        'NSS PHOTOGRPAHS/MAINTAINANCE VISIT\'25': 'Maintenance Visit 2025'
    }

    assets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')

    for folder, album_name in folder_to_album.items():
        folder_path = os.path.join(assets_path, folder)
        if os.path.exists(folder_path):
            photos = []
            for filename in os.listdir(folder_path):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    # Use direct path to assets folder
                    photo_url = f"http://localhost:5000/assets/{folder}/{filename}"
                    photos.append({
                        "name": filename,
                        "url": photo_url,
                        "filename": f"{folder}/{filename}"
                    })

            # Create album with photos
            album_data = {
                "name": album_name,
                "photos": photos
            }
            albums_col.insert_one(album_data)
            print(f"Created album '{album_name}' with {len(photos)} photos")
        else:
            print(f"Folder '{folder}' not found")

    print("Album population completed!")

if __name__ == '__main__':
    populate_albums()
