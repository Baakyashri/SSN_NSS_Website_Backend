from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from agent.llm_factory import get_llm
from agent.prompts.system_prompt import SYSTEM_PROMPT

from agent.tools.activity_tools import get_upcoming_events
from agent.tools.generic_tools import (
    query_records,
    aggregate_records,
    get_volunteer_hours_summary,
    mutate_record,
    schedule_job,
    send_notification,
)
from agent.tools.report_tools import (
    semantic_search_reports,
    request_report,
)

TOOLS = [
    get_upcoming_events,
    query_records,
    aggregate_records,
    get_volunteer_hours_summary,
    mutate_record,
    schedule_job,
    send_notification,
    semantic_search_reports,
    request_report,
]

llm, llm_info = get_llm()
llm_with_tools = llm.bind_tools(TOOLS)


def agent_node(state: dict, config: RunnableConfig):

    messages     = state["messages"]
    print("LAST MESSAGE:", messages[-1].content)
    print("MESSAGE COUNT:", len(messages))
    configurable = config.get("configurable", {})

    user_id    = configurable.get("user_id",    "unknown")
    user_email = configurable.get("user_email", "unknown")
    role       = configurable.get("role",       "volunteer")
    # ADD THIS TEMPORARILY
    print(f"AGENT NODE — role: {role}, user_id: {user_id}")

    # ── Role-specific behaviour instructions ─────────────────
    role = role.lower()
    if role == "admin":
        role_context = """
                You are currently assisting an ADMIN user.
                You CAN write to: users, activities, announcements, registrations,
                and all agent_* collections.

                When admin asks to add a user, collect these fields conversationally
                one by one before calling mutate_record:
                    Required : name, email, password (auto-generate a temp one), role
                    Optional : department, year, phone

                When admin asks to add an activity, collect:
                    Required : title, description, date, attendance_hours, no_of_volunteers
                    Optional : location, category, day_of_week, required_tags

                When admin asks to add an announcement, collect:
                    Required : title, content
                    Optional : category

                Always confirm with the admin before calling mutate_record — summarise
                what you are about to insert and ask "Shall I proceed?".
                After inserting, confirm the record was added and mention it is now
                visible in the admin dashboard and MongoDB.

                REGISTRATION WORKFLOW — follow exactly:
                Step 1: Call query_records to confirm the activity exists and has open slots
                        filters={"_id": activity_id}, collection="activities"
                Step 2: Call query_records to check volunteer is not already registered
                        filters={"user_id": user_id, "activity_id": activity_id},
                        collection="registrations"
                Step 3: Call mutate_record ONLY after steps 1 and 2 pass
                        operation="insert", collection="registrations",
                        payload={
                            "user_id": user_id,
                            "user_email": user_email,
                            "activity_id": activity_id,
                            "activity_title": title,
                            "registered_at": datetime now,
                            "status": "registered",
                            "attendance_status": "pending"
                        }
                Step 4: Report the ACTUAL return value from mutate_record to the user.
                        Do NOT say success unless tool returned status: success.
                """
    else:
        role_context = """
                You are currently assisting a VOLUNTEER user.
                You can read all data but can only write to:
                    registrations, agent_volunteer_profiles,
                    agent_scheduled_jobs, agent_subscriptions, agent_memory.

                You CANNOT add users, activities, or announcements — those are admin actions.
                If the volunteer asks for admin operations, politely explain they need
                admin access for that.
                """

    user_context = f"""
        CURRENT LOGGED-IN USER:
            user_id    : {user_id}
            email      : {user_email}
            role       : {role}

        Always pass user_id="{user_id}" and role="{role}" when calling mutate_record.
        When the user asks "who am I", answer directly from above — no tool call needed.
        """

    full_system_prompt = user_context + role_context + "\n\n" + SYSTEM_PROMPT

    response = llm_with_tools.invoke(
        [SystemMessage(content=full_system_prompt)] + messages
    )

    return {"messages": [response]}