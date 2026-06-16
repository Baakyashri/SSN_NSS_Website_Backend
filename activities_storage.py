"""
Shared storage for activities data
This simulates a database for activities
"""

# In-memory storage for activities
ACTIVITIES_STORAGE = [
    {
        "id": 1,
        "title": "Blood Donation Camp",
        "description": "Annual blood donation drive organized by NSS",
        "date": "2025-09-16",
        "location": "SSN Campus",
        "photos": [
            {
                "filename": "blood_camp.JPG",
                "original_name": "blood_camp.JPG",
                "url": "/uploads/blood_camp.JPG"
            }
        ],
        "reports": [],
        "status": "completed"
    },
    {
        "id": 2,
        "title": "Tree Plantation Drive",
        "description": "Environmental initiative to plant 100 saplings",
        "date": "2025-09-20",
        "location": "Campus Garden",
        "photos": [],
        "reports": [],
        "status": "upcoming"
    },
    {
        "id": 3,
        "title": "Community Health Checkup",
        "description": "Free health checkup for local community",
        "date": "2025-09-25",
        "location": "Nearby Village",
        "photos": [],
        "reports": [],
        "status": "upcoming"
    }
]

def get_all_activities():
    """Get all activities"""
    return ACTIVITIES_STORAGE.copy()

def get_latest_activities(limit=3):
    """Get latest activities"""
    return ACTIVITIES_STORAGE[:limit]

def add_activity(activity_data):
    """Add a new activity"""
    import time
    new_activity = {
        "id": int(time.time()),  # Simple ID generation
        "title": activity_data.get("title"),
        "description": activity_data.get("description"),
        "date": activity_data.get("date"),
        "location": activity_data.get("location", "SSN Campus"),
        "photos": activity_data.get("photos", []),
        "reports": activity_data.get("reports", []),
        "status": activity_data.get("status", "upcoming")
    }
    ACTIVITIES_STORAGE.insert(0, new_activity)  # Add to beginning
    return new_activity

def update_activity(activity_id, activity_data):
    """Update an existing activity"""
    for i, activity in enumerate(ACTIVITIES_STORAGE):
        if activity["id"] == activity_id:
            ACTIVITIES_STORAGE[i].update(activity_data)
            return ACTIVITIES_STORAGE[i]
    return None

def delete_activity(activity_id):
    """Delete an activity"""
    global ACTIVITIES_STORAGE
    ACTIVITIES_STORAGE = [activity for activity in ACTIVITIES_STORAGE if activity["id"] != activity_id]
    return True
