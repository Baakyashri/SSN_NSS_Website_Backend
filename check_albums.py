from db import db

def check_database():
    print("Checking database contents...")

    # Check albums
    albums_col = db['albums']
    albums = list(albums_col.find({}, {"_id": 0}))
    print(f"Albums: {len(albums)} found")
    for album in albums:
        print(f"  - {album}")

    # Check activities
    activities_col = db['activities']
    activities = list(activities_col.find({}, {"_id": 0}))
    print(f"Activities: {len(activities)} found")
    for activity in activities:
        print(f"  - {activity['title']} ({activity['date']})")

if __name__ == '__main__':
    check_database()
