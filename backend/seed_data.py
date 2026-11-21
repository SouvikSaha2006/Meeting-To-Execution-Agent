"""
seed_data.py — Realistic multi-meeting transcripts for instant judge demos.

Design goals:
  Meeting 1 (Sprint 14 Kickoff — Nov 14):
    ✅ 3 clean verified action items (owner + deadline clearly stated)
    ⚠️  2 ambiguous action items (missing owner or deadline)
    📋 3 clear decisions
    
  Meeting 2 (Architecture & Scope Sync — Nov 21):
    ✅ 2 clean action items
    🔥 2 cross-meeting conflicts:
         - Database: PostgreSQL → MongoDB
         - Launch date: Nov 29 → Nov 22 (moved up WITHOUT cutting scope)
    🔗 1 dependency blocker (Task B depends on Task A, but B deadline is before A)
    ⚠️  1 ambiguous item (missing deadline)

Usage:
  POST /api/demo/seed          — resets DB and loads both meetings
  POST /api/demo/load-meeting-1 — loads Meeting 1 only
  POST /api/demo/load-meeting-2 — loads Meeting 2 only (requires Meeting 1 approved first)
"""

MEETING_1_TITLE = "Sprint 14 Kickoff - Nov 14"
MEETING_1_DATE = "2024-11-14"
MEETING_1_TRANSCRIPT = """
Sarah (PM): Alright everyone, let's get Sprint 14 kicked off. We have a lot to cover today before the launch on November 29th. I want to make sure everyone is aligned on priorities.

David (CTO): Sounds good. I've been reviewing the architecture and I'm confident we should go with PostgreSQL as our primary database. It gives us the ACID compliance we need for the billing module, and the team has existing expertise. I'm making this call today.

Sarah (PM): Agreed. So the decision is PostgreSQL. That's locked. Now, who's taking the database schema migration work?

David (CTO): Marcus, can you own that? The initial schema needs to be done by November 18th so the backend team can start writing queries.

Marcus (Backend Lead): Yeah, I can do that. November 18th works. I'll own the schema design and migration scripts.

Sarah (PM): Perfect. And Marcus, once the schema is ready, the API layer needs to be built on top of it. Can you also own the REST API endpoints for the user management module?

Marcus (Backend Lead): The API work I can do, but I'll need the schema to be done first obviously. I'd say give me until November 22nd for the first version of the user API.

Sarah (PM): Great. So Marcus owns both: schema by the 18th, user API by the 22nd. That dependency is noted.

Priya (Frontend Lead): From the frontend side, I'll need those API endpoints to build the dashboard. So my work on the user dashboard is blocked until Marcus ships the API.

Sarah (PM): Priya, when can you deliver the user dashboard once you have the APIs?

Priya (Frontend Lead): If I get the APIs on the 22nd, I can have the dashboard ready by November 26th, which gives us 3 days before launch on the 29th for QA.

Sarah (PM): Perfect. Priya owns the user dashboard, deadline November 26th, dependent on Marcus's API.

David (CTO): One thing I want to flag — we need a CI/CD pipeline set up before anyone starts pushing to main. This is critical.

Sarah (PM): Who's taking CI/CD setup?

David (CTO): That should be... hmm. We should figure this out. Someone from the DevOps side.

Sarah (PM): Let's circle back on that. We need to identify a DevOps owner. I'll put it as a discussion item. Actually, let me add it as an open action — we need to assign CI/CD ownership.

Marcus (Backend Lead): Also, we haven't decided on our caching strategy yet. Redis or Memcached?

David (CTO): Good point. Let's evaluate options. I'd lean Redis because of its richer data structures, but let's not decide today — let me think about it this week.

Sarah (PM): Okay, Redis evaluation is an open item — no decision yet, we'll revisit. Now, regarding the sprint ceremonies: we're doing daily standups at 9 AM, sprint review on November 28th at 2 PM, and retrospective immediately after. That's locked in by me as PM.

Tom (QA Lead): I wanted to bring up the testing strategy. We need end-to-end tests before launch.

Sarah (PM): Tom, can you own the E2E test suite setup?

Tom (QA Lead): I can start immediately but I'll need the staging environment to be ready. When will that be available?

David (CTO): Staging should be up by November 20th.

Tom (QA Lead): Okay then I'll have the E2E test suite ready by November 25th. I own that.

Sarah (PM): Great. So to summarize the key decisions: PostgreSQL is our database, launch is November 29th, sprint ceremonies are locked. Action items: Marcus owns schema by 18th and API by 22nd, Priya owns dashboard by 26th (dependent on API), Tom owns E2E tests by 25th, and we have two open items: CI/CD ownership and caching strategy. Meeting adjourned.
"""

MEETING_2_TITLE = "Architecture & Scope Sync - Nov 21"
MEETING_2_DATE = "2024-11-21"
MEETING_2_TRANSCRIPT = """
Sarah (PM): Emergency sync everyone. We have some critical changes to discuss. First, I'll address the elephant in the room — the client called yesterday and they want the launch moved up to November 22nd. That is tomorrow.

David (CTO): Wait, that's impossible. We haven't even finished the API layer yet, the dashboard is not built, and QA hasn't started. Moving the launch up by a week without cutting scope is completely unrealistic.

Sarah (PM): I understand the concern, but the client is firm. The launch date is now November 22nd. No scope is being cut — the full feature set needs to ship. I'm making this call as PM, the launch moves to November 22nd.

David (CTO): [frustrated] That conflicts with every deadline we set last week. Marcus's API was due November 22nd, and now that's also the launch date? This is a blocker.

Sarah (PM): We'll need to accelerate. David, can the team work over the weekend?

David (CTO): We can try, but I want it on record that this creates blocker risk on the dashboard and QA work. Tom, are you aware that your E2E tests need to be done before launch?

Tom (QA Lead): I literally just found out launch is tomorrow. This is a problem. I haven't even started because staging wasn't ready until yesterday.

Sarah (PM): Tom, what can you realistically deliver by end of day today?

Tom (QA Lead): I can do smoke tests only. Full E2E suite is out of the question for tomorrow.

Sarah (PM): Fine. Tom will deliver smoke tests by end of today. The full E2E suite is deprioritized.

David (CTO): Now, there's another thing I need to bring up. I've been doing more research this week and I think we need to switch our database from PostgreSQL to MongoDB. 

Sarah (PM): You decided PostgreSQL last week.

David (CTO): I know, but the more I look at our data model for the analytics module — it's document-oriented. MongoDB will be significantly more efficient. I'm making the call: we're switching to MongoDB.

Sarah (PM): That's a major architectural change a week into the sprint. Marcus already wrote the schema migrations.

David (CTO): Marcus, the PostgreSQL schema work you did — can we convert it to MongoDB collections?

Marcus (Backend Lead): I mean... yes, but it'll take time. The user management schema specifically has a lot of relational joins. MongoDB is going to complicate that.

David (CTO): It's the right long-term call. We use MongoDB. Decision made.

Sarah (PM): Okay, so David is officially deciding: we're migrating from PostgreSQL to MongoDB. Marcus, you need to redo the schema work for MongoDB. What's your new deadline?

Marcus (Backend Lead): I'll need until November 25th to redo the schema for MongoDB. But remember, the user API also depends on this schema, and it was due November 22nd. That's going to slip too.

Sarah (PM): Marcus, let's say you own the MongoDB schema redesign, deadline November 25th. We'll reassess the API deadline after.

David (CTO): Also, we really need to talk about performance monitoring. With the new MongoDB setup, we need Datadog integrated for query performance tracking. Someone needs to own the Datadog integration.

Sarah (PM): Who from the team can take Datadog?

Marcus (Backend Lead): It could be me after the MongoDB schema work, but I don't have a specific timeline in mind right now.

Sarah (PM): Let's flag that as a needed action item. We need a Datadog integration owner and deadline — that's not assigned yet.

Priya (Frontend Lead): Can I raise something? My dashboard work depends on Marcus's user API, and that's now slipping. When will I actually get the APIs?

Sarah (PM): Priya, we'll update you on API dates once Marcus knows. For now, start with any static UI components that don't require API data.

Priya (Frontend Lead): Fine. I'll start on static components now. I'll have the static layouts done by November 23rd. I own that.

David (CTO): One more thing — the CI/CD pipeline. We still don't have an owner for that. I'm going to mandate that we sort this out today.

Sarah (PM): David, do you want to own CI/CD setup yourself or delegate?

David (CTO): I'll personally set up the CI/CD pipeline using GitHub Actions. I commit to having a basic pipeline with build, test, and deploy stages ready by November 24th.

Sarah (PM): Perfect. David owns CI/CD via GitHub Actions, deadline November 24th. Okay, to summarize today's decisions: Launch moved to November 22nd, database switched from PostgreSQL to MongoDB. Action items: Marcus owns MongoDB schema redesign by November 25th, Priya owns static layouts by November 23rd, David owns CI/CD by November 24th. Tom's E2E tests are deprioritized. Datadog integration still needs an owner. We're done.
"""

# ── Canonical extraction payloads for Meeting 1 ───────────────────────────────
# (Used by load_meeting_1 to bypass LLM and inject deterministic demo data)
MEETING_1_DECISIONS = [
    {
        "topic_key": "database_choice",
        "statement": "The team will use PostgreSQL as the primary database for ACID compliance and team expertise.",
        "decided_by": "David (CTO)",
        "verbatim_quote": "I'm confident we should go with PostgreSQL as our primary database. It gives us the ACID compliance we need for the billing module, and the team has existing expertise. I'm making this call today.",
        "confidence": "HIGH",
    },
    {
        "topic_key": "launch_date",
        "statement": "The product launch is scheduled for November 29th, 2024.",
        "decided_by": "Sarah (PM)",
        "verbatim_quote": "We have a lot to cover today before the launch on November 29th.",
        "confidence": "HIGH",
    },
    {
        "topic_key": "sprint_ceremonies",
        "statement": "Sprint 14 ceremonies: daily standups at 9AM, sprint review November 28th at 2PM, retrospective immediately after.",
        "decided_by": "Sarah (PM)",
        "verbatim_quote": "We're doing daily standups at 9 AM, sprint review on November 28th at 2 PM, and retrospective immediately after. That's locked in by me as PM.",
        "confidence": "HIGH",
    },
]

MEETING_1_ACTION_ITEMS = [
    {
        "title": "Design and implement PostgreSQL database schema migrations",
        "description": "Design the initial PostgreSQL database schema including all tables for user management, billing module, and core entities. Write SQLAlchemy migration scripts.",
        "owner": "Marcus",
        "deadline_iso": "2024-11-18",
        "deadline_raw": "November 18th",
        "priority": "HIGH",
        "depends_on_task_title": None,
        "verbatim_quote": "Marcus, can you own that? The initial schema needs to be done by November 18th so the backend team can start writing queries.",
        "status": "READY_TO_APPROVE",
        "missing_fields": None,
        "clarification_prompt": None,
    },
    {
        "title": "Build REST API endpoints for user management module",
        "description": "Implement the full REST API layer for user management including authentication, profile management, and permissions. Must follow the finalized PostgreSQL schema.",
        "owner": "Marcus",
        "deadline_iso": "2024-11-22",
        "deadline_raw": "November 22nd",
        "priority": "HIGH",
        "depends_on_task_title": "Design and implement PostgreSQL database schema migrations",
        "verbatim_quote": "The API work I can do, but I'll need the schema to be done first obviously. I'd say give me until November 22nd for the first version of the user API.",
        "status": "READY_TO_APPROVE",
        "missing_fields": None,
        "clarification_prompt": None,
    },
    {
        "title": "Build user dashboard frontend",
        "description": "Design and implement the user-facing dashboard UI with all sprint 14 features. Dependent on user management API being available.",
        "owner": "Priya",
        "deadline_iso": "2024-11-26",
        "deadline_raw": "November 26th",
        "priority": "HIGH",
        "depends_on_task_title": "Build REST API endpoints for user management module",
        "verbatim_quote": "If I get the APIs on the 22nd, I can have the dashboard ready by November 26th, which gives us 3 days before launch on the 29th for QA.",
        "status": "READY_TO_APPROVE",
        "missing_fields": None,
        "clarification_prompt": None,
    },
    {
        "title": "Set up end-to-end test suite",
        "description": "Create a comprehensive end-to-end test suite covering all critical user flows before the November 29th launch.",
        "owner": "Tom",
        "deadline_iso": "2024-11-25",
        "deadline_raw": "November 25th",
        "priority": "HIGH",
        "depends_on_task_title": None,
        "verbatim_quote": "Okay then I'll have the E2E test suite ready by November 25th. I own that.",
        "status": "READY_TO_APPROVE",
        "missing_fields": None,
        "clarification_prompt": None,
    },
    {
        "title": "Assign CI/CD pipeline owner and set up infrastructure",
        "description": "Identify and assign a DevOps owner for the CI/CD pipeline. Set up automated build, test, and deployment pipeline before team merges to main branch.",
        "owner": None,
        "deadline_iso": None,
        "deadline_raw": None,
        "priority": "HIGH",
        "depends_on_task_title": None,
        "verbatim_quote": "Who's taking CI/CD setup? David (CTO): That should be... hmm. We should figure this out. Someone from the DevOps side.",
        "status": "NEEDS_CLARIFICATION",
        "missing_fields": ["owner", "deadline"],
        "clarification_prompt": "Who from the DevOps team will own the CI/CD pipeline setup, and by what date must this be completed?",
    },
    {
        "title": "Evaluate and decide on caching strategy (Redis vs Memcached)",
        "description": "Research and evaluate Redis vs Memcached for the application caching layer. Present recommendation and get CTO sign-off.",
        "owner": "David",
        "deadline_iso": None,
        "deadline_raw": "this week",
        "priority": "MEDIUM",
        "depends_on_task_title": None,
        "verbatim_quote": "Good point. Let's evaluate options. I'd lean Redis because of its richer data structures, but let's not decide today — let me think about it this week.",
        "status": "NEEDS_CLARIFICATION",
        "missing_fields": ["deadline"],
        "clarification_prompt": "David mentioned he would evaluate caching options 'this week' but no specific deadline was set. What is the exact deadline for the caching strategy decision?",
    },
]

# ── Canonical extraction payloads for Meeting 2 ───────────────────────────────
MEETING_2_DECISIONS = [
    {
        "topic_key": "launch_date",
        "statement": "The product launch is moved up to November 22nd, 2024 (from November 29th) with no scope reduction.",
        "decided_by": "Sarah (PM)",
        "verbatim_quote": "The launch date is now November 22nd. No scope is being cut — the full feature set needs to ship. I'm making this call as PM, the launch moves to November 22nd.",
        "confidence": "HIGH",
    },
    {
        "topic_key": "database_choice",
        "statement": "The database is switched from PostgreSQL to MongoDB for better fit with the document-oriented analytics data model.",
        "decided_by": "David (CTO)",
        "verbatim_quote": "I've been doing more research this week and I think we need to switch our database from PostgreSQL to MongoDB. I'm making the call: we're switching to MongoDB.",
        "confidence": "HIGH",
    },
]

MEETING_2_ACTION_ITEMS = [
    {
        "title": "Redesign database schema for MongoDB collections",
        "description": "Convert the existing PostgreSQL relational schema to MongoDB document-based collections. Address user management schema complexity and ensure no data model regressions.",
        "owner": "Marcus",
        "deadline_iso": "2024-11-25",
        "deadline_raw": "November 25th",
        "priority": "HIGH",
        "depends_on_task_title": None,
        "verbatim_quote": "I'll need until November 25th to redo the schema for MongoDB.",
        "status": "READY_TO_APPROVE",
        "missing_fields": None,
        "clarification_prompt": None,
    },
    {
        "title": "Build static UI layouts for dashboard",
        "description": "Implement static frontend dashboard layouts and components that do not require live API data, to progress frontend work while backend API timeline is reassessed.",
        "owner": "Priya",
        "deadline_iso": "2024-11-23",
        "deadline_raw": "November 23rd",
        "priority": "MEDIUM",
        "depends_on_task_title": "Redesign database schema for MongoDB collections",
        "verbatim_quote": "I'll start on static components now. I'll have the static layouts done by November 23rd. I own that.",
        "status": "READY_TO_APPROVE",
        "missing_fields": None,
        "clarification_prompt": None,
    },
    {
        "title": "Set up CI/CD pipeline with GitHub Actions",
        "description": "Implement a CI/CD pipeline using GitHub Actions with stages: build, test, and deploy. Must be functional before team begins merging feature branches.",
        "owner": "David",
        "deadline_iso": "2024-11-24",
        "deadline_raw": "November 24th",
        "priority": "HIGH",
        "depends_on_task_title": None,
        "verbatim_quote": "I'll personally set up the CI/CD pipeline using GitHub Actions. I commit to having a basic pipeline with build, test, and deploy stages ready by November 24th.",
        "status": "READY_TO_APPROVE",
        "missing_fields": None,
        "clarification_prompt": None,
    },
    {
        "title": "Integrate Datadog for MongoDB query performance monitoring",
        "description": "Set up Datadog integration to monitor MongoDB query performance, slow query alerts, and infrastructure metrics for the production environment.",
        "owner": None,
        "deadline_iso": None,
        "deadline_raw": None,
        "priority": "MEDIUM",
        "depends_on_task_title": "Redesign database schema for MongoDB collections",
        "verbatim_quote": "We need Datadog integrated for query performance tracking. Someone needs to own the Datadog integration.",
        "status": "NEEDS_CLARIFICATION",
        "missing_fields": ["owner", "deadline"],
        "clarification_prompt": "Who will own the Datadog integration, and by what date must it be completed? Marcus was suggested but no commitment was made.",
    },
]
