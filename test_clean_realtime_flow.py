import asyncio
import os
import sys

# Ensure backend can be imported
sys.path.insert(0, ".")

from backend.database import AsyncSessionLocal, init_db
from backend.main import demo_reset, weekly_digest, ask_memory
from backend.schemas import MemoryAskRequest
from backend.agent_pipeline import parse_transcript, stage_for_approval, _smart_fallback_extraction, detect_conflicts_and_duplicates
from backend.models import Meeting, Decision, ExecutionTask, StagingItem
from sqlalchemy import select, func

async def run_tests():
    await init_db()

    # Step 1: Run demo_reset to start with a clean 0-record workspace
    async with AsyncSessionLocal() as db:
        reset_res = await demo_reset(db)
        print("Reset response:", reset_res)

        # Check all tables are 0
        for model in [Meeting, Decision, ExecutionTask, StagingItem]:
            count = (await db.execute(select(func.count(model.id)))).scalar()
            print(f"Count of {model.__name__}: {count}")
            assert count == 0, f"Expected 0 for {model.__name__}, got {count}"
        print("✓ Step 1: Reset completely clears tables to 0 records")

    # Step 2: Test empty state endpoints
    async with AsyncSessionLocal() as db:
        empty_digest = await weekly_digest(db)
        print("Empty digest stats:", empty_digest.summary_stats)
        assert empty_digest.summary_stats["total_tasks"] == 0
        assert empty_digest.by_owner == []
        print("✓ Step 2a: Empty weekly digest returned cleanly without auto-seeding")

        empty_ask = await ask_memory(MemoryAskRequest(question="Why did our DB choice change?"), db)
        print("Empty ask answer:", empty_ask.answer)
        assert empty_ask.answer == "No meetings have been ingested yet. Paste or upload a transcript above to build your organizational memory."
        assert empty_ask.citations == []
        assert empty_ask.related_task_ids == []
        print("✓ Step 2b: Empty memory query returns exact requested notice with 0 citations")

    # Step 3: Ingest Meeting 1 with custom names (Souvik & Manas)
    transcript_1 = """
[10:00 AM] Souvik (Lead): Team, we are standardizing on PostgreSQL 15 as our primary database. I am making this call for data integrity.
Manas: Sounds good. I will design the initial PostgreSQL schemas by Nov 25.
Souvik: Someone needs to set up the CI/CD pipeline by Nov 27.
"""
    async with AsyncSessionLocal() as db:
        m1 = Meeting(title="Architecture Sync #1", meeting_date="2024-11-20", raw_transcript=transcript_1)
        db.add(m1)
        await db.flush()

        segments1 = parse_transcript(transcript_1)
        extraction1 = _smart_fallback_extraction(segments1, m1.title, m1.meeting_date)
        dec_meta1, act_meta1 = await detect_conflicts_and_duplicates(extraction1, db, m1.id)
        staged1 = await stage_for_approval(dec_meta1, act_meta1, m1.id, db)
        await db.commit()

        print(f"Meeting 1 staged {len(staged1)} items:")
        for s in staged1:
            print(f"  - [{s.state}] {s.item_type}: {s.verbatim_quote}")

        # Approve all ready items so they become decisions and tasks
        for s in staged1:
            if s.state == "READY_TO_APPROVE":
                from backend.main import _approve_single_item
                await _approve_single_item(s, db)
        await db.commit()
        print("✓ Step 3: Meeting 1 ingested and approved with Souvik & Manas")

    # Step 4: Ingest Meeting 2 with a conflicting decision (Manas switches to MongoDB)
    transcript_2 = """
[11:00 AM] Manas: I've evaluated our query patterns and I am deciding right now that we switch from PostgreSQL to MongoDB.
Manas: I'll build the new MongoDB collections by Nov 28.
Souvik: Assign Alex to build the API integration by Nov 29.
"""
    async with AsyncSessionLocal() as db:
        m2 = Meeting(title="Database Pivot Sync", meeting_date="2024-11-22", raw_transcript=transcript_2)
        db.add(m2)
        await db.flush()

        segments2 = parse_transcript(transcript_2)
        extraction2 = _smart_fallback_extraction(segments2, m2.title, m2.meeting_date)
        dec_meta2, act_meta2 = await detect_conflicts_and_duplicates(extraction2, db, m2.id)
        staged2 = await stage_for_approval(dec_meta2, act_meta2, m2.id, db)
        await db.commit()

        print(f"Meeting 2 staged {len(staged2)} items:")
        for s in staged2:
            print(f"  - [{s.state}] {s.item_type}: {s.verbatim_quote}")

        # Verify conflict detected
        conflicts = [s for s in staged2 if s.state == "CONFLICT_DETECTED"]
        assert len(conflicts) >= 1, "Expected conflict on database pivot"
        print("✓ Step 4: Cross-meeting conflict detected against Souvik's decision")

    # Step 5: Test dynamic Memory Synthesis (POST /api/memory/ask)
    async with AsyncSessionLocal() as db:
        # 5a. Conflict query
        ask_conflict = await ask_memory(MemoryAskRequest(question="Why did our DB choice change?"), db)
        print("\n--- ASK MEMORY: DB CHANGE ---")
        print("Answer:", ask_conflict.answer)
        print("Citations:")
        for c in ask_conflict.citations:
            print(f"  [{c.speaker}] '{c.meeting_title}' ({c.meeting_date}): {c.quote}")
            assert c.speaker in ("Souvik", "Manas", "Team"), f"Unexpected speaker: {c.speaker}"
            assert c.speaker != "Unassigned"
        assert "Souvik" in ask_conflict.answer or any(c.speaker == "Souvik" for c in ask_conflict.citations)
        assert "Manas" in ask_conflict.answer or any(c.speaker == "Manas" for c in ask_conflict.citations)

        # Ensure NO canned names present anywhere
        for canned in ["david", "marcus", "priya", "tom", "sarah"]:
            assert canned not in ask_conflict.answer.lower(), f"Found canned name {canned} in answer!"
        print("✓ Step 5a: DB conflict query dynamically synthesized from live records with real speakers")

        # 5b. Tasks due soon query
        ask_tasks = await ask_memory(MemoryAskRequest(question="Who has tasks due soon?"), db)
        print("\n--- ASK MEMORY: TASKS DUE SOON ---")
        print("Answer:", ask_tasks.answer)
        print("Citations:")
        for c in ask_tasks.citations:
            print(f"  [{c.speaker}] '{c.meeting_title}': {c.quote}")
            assert c.speaker != "Unassigned"
        assert "Manas" in ask_tasks.answer or "Souvik" in ask_tasks.answer
        for canned in ["david", "marcus", "priya", "tom", "sarah"]:
            assert canned not in ask_tasks.answer.lower(), f"Found canned name {canned} in answer!"
        print("✓ Step 5b: Tasks due soon query dynamically lists real owners")

        # 5c. Person-specific query: Souvik
        ask_souvik = await ask_memory(MemoryAskRequest(question="What did Souvik decide or own?"), db)
        print("\n--- ASK MEMORY: SOUVIK ---")
        print("Answer:", ask_souvik.answer)
        assert "Souvik" in ask_souvik.answer
        for canned in ["david", "marcus", "priya", "tom", "sarah"]:
            assert canned not in ask_souvik.answer.lower(), f"Found canned name {canned} in answer!"
        print("✓ Step 5c: Person query for Souvik synthesized accurately")

    # Step 6: Test Weekly Digest with live data
    async with AsyncSessionLocal() as db:
        digest = await weekly_digest(db)
        print("\n--- WEEKLY DIGEST ---")
        print("Owners in digest:", [o.owner for o in digest.by_owner])
        assert any("Manas" in o.owner for o in digest.by_owner)
        for canned in ["david", "marcus", "priya", "tom", "sarah"]:
            assert not any(canned in o.owner.lower() for o in digest.by_owner)
        print("✓ Step 6: Weekly digest populated exclusively with real participants")

    print("\n🎉 ALL REAL-TIME VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_tests())
