from langchain.tools import tool
from models.mongo import activities_collection

@tool
def get_upcoming_events():
    """
    Returns all upcoming NSS activities.
    Use when user asks about upcoming events,
    future activities, next programs or camps.
    """

    activities = list(
        activities_collection.find(
            {"status": "upcoming"},
            {"_id": 0}
        )
    )

    return str(activities)