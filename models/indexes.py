from models.mongo import registrations_collection

def create_indexes():
    registrations_collection.create_index(
        [
            ("user_id", 1),
            ("activity_id", 1)
        ],
        unique=True
    )


registrations_collection.create_index("user_id")
registrations_collection.create_index("activity_id")