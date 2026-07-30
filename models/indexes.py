from models.mongo import db, registrations_collection, activities_collection

def create_indexes():
    # Registrations Indexes
    registrations_collection.create_index(
        [
            ("user_id", 1),
            ("activity_id", 1)
        ],
        unique=True
    )
    registrations_collection.create_index("user_id")
    registrations_collection.create_index("activity_id")

    # Activities Indexes (Standard)
    activities_collection.create_index("status")
    activities_collection.create_index("title")

    # Agent Collections TTL Indexes
    # agent_audit_log: 90 days (7776000 seconds)
    db.agent_audit_log.create_index("timestamp", expireAfterSeconds=7776000)
    
    # agent_memory: 30 days (2592000 seconds)
    db.agent_memory.create_index("updated_at", expireAfterSeconds=2592000)
    
    # agent_report_jobs: 30 days (2592000 seconds)
    db.agent_report_jobs.create_index("updated_at", expireAfterSeconds=2592000)