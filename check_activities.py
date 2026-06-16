from db import db

def check_activities():
    activities_col = db['activities']
    activities = list(activities_col.find())

    print(f"Total activities in database: {len(activities)}")

    for i, activity in enumerate(activities):
        title = activity.get('title', 'No title')
        photos = activity.get('photos', [])
        print(f"\nActivity {i+1}: {title}")
        print(f"Photos count: {len(photos)}")
        if photos:
            print("Photos:")
            for j, photo in enumerate(photos):
                print(f"  Photo {j+1}: {photo}")
        else:
            print("No photos")

if __name__ == '__main__':
    check_activities()
