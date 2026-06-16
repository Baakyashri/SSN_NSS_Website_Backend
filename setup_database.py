from db import db
from werkzeug.security import generate_password_hash

def setup_database():
    """Initialize the database with default admin user and collections"""

    # Create collections if they don't exist
    collections = ['users', 'activities', 'announcements', 'highlights']
    for collection_name in collections:
        if collection_name not in db.list_collection_names():
            db.create_collection(collection_name)
            print(f"Created collection: {collection_name}")

    # Check if admin user exists
    users_col = db['users']
    admin_user = users_col.find_one({'email': 'admin@nss.com'})

    if not admin_user:
        # Create default admin user
        admin_data = {
            'email': 'admin@nss.com',
            'password': generate_password_hash('admin123'),
            'role': 'admin'
        }
        users_col.insert_one(admin_data)
        print("Created default admin user: admin@nss.com / admin123")
    else:
        print("Admin user already exists")

    # Add some sample data
    announcements_col = db['announcements']
    if announcements_col.count_documents({}) == 0:
        sample_announcements = [
            {
                'activityName': 'Blood Donation Camp',
                'activityDescription': 'Join us for the annual blood donation camp on September 16th'
            },
            {
                'activityName': 'Tree Plantation Drive',
                'activityDescription': 'Help us plant 100 trees in the campus area'
            }
        ]
        announcements_col.insert_many(sample_announcements)
        print("Added sample announcements")

    highlights_col = db['highlights']
    if highlights_col.count_documents({}) == 0:
        sample_highlights = [
            {
                'title': 'NSS Day Celebration',
                'description': 'Successfully celebrated NSS Day with various activities and community service'
            },
            {
                'title': 'Clean Campus Initiative',
                'description': 'Led a campus-wide cleanliness drive with 200+ volunteers'
            }
        ]
        highlights_col.insert_many(sample_highlights)
        print("Added sample highlights")

    # Add sample activities
    activities_col = db['activities']
    if activities_col.count_documents({}) == 0:
        sample_activities = [
            {
                'title': 'Beach Cleanup Drive',
                'description': 'Volunteers participated in cleaning the local beach and raising awareness about marine pollution.',
                'date': '2025-09-20',
                'location': 'Marina Beach, Chennai'
            },
            {
                'title': 'Blood Donation Camp',
                'description': 'Annual blood donation camp organized in collaboration with local hospitals.',
                'date': '2025-09-17',
                'location': 'SSN College Auditorium'
            },
            {
                'title': 'Tree Plantation Drive',
                'description': 'Planted 100 saplings in the campus and surrounding areas to promote environmental sustainability.',
                'date': '2025-06-15',
                'location': 'SSN College Campus'
            },
            {
                'title': 'Maintenance Visit',
                'description': 'Visited local villages to conduct maintenance and repair work on community infrastructure.',
                'date': '2025-09-23',
                'location': 'Thandalam Village'
            }
        ]
        activities_col.insert_many(sample_activities)
        print("Added sample activities")

    # Add sample albums
    albums_col = db['albums']
    if albums_col.count_documents({}) == 0:
        sample_albums = [
            {
                'name': 'Annual Camp 2025',
                'photos': []
            },
            {
                'name': 'Beach Cleanup Drive',
                'photos': []
            },
            {
                'name': 'Blood Donation Camp',
                'photos': []
            },
            {
                'name': 'Tree Plantation',
                'photos': []
            }
        ]
        albums_col.insert_many(sample_albums)
        print("Added sample albums")

    print("Database setup completed!")

if __name__ == '__main__':
    setup_database()
