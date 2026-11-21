import sys
sys.path.insert(0, 'backend')
from agent_pipeline import (
    parse_transcript,
    _smart_fallback_extraction,
    normalize_speaker_name,
    _find_decision_conflict,
    analyze_blast_radius,
    generate_nudge_draft,
    LLMDecision,
    LLMActionItem,
    ConflictMeta,
)

def test_normalization():
    assert normalize_speaker_name('[Souvik (Lead)]') == 'Souvik', f"Got {normalize_speaker_name('[Souvik (Lead)]')}"
    assert normalize_speaker_name('**Manas (Backend):**') == 'Manas', f"Got {normalize_speaker_name('**Manas (Backend):**')}"
    assert normalize_speaker_name('Manas Kumar (Tech Lead)') == 'Manas Kumar', f"Got {normalize_speaker_name('Manas Kumar (Tech Lead)')}"
    assert normalize_speaker_name('Souvik:') == 'Souvik', f"Got {normalize_speaker_name('Souvik:')}"
    assert normalize_speaker_name('[00:14:22] Alex') == 'Alex', f"Got {normalize_speaker_name('[00:14:22] Alex')}"
    print("✓ test_normalization passed")

def test_multi_format_parsing():
    transcript = """
[10:00 AM] Souvik: Team, we need to talk about database architecture.
Souvik: I am deciding right now that we switch from PostgreSQL to MongoDB.
**Manas (Backend Lead):** Sounds good. I'll build the REST API endpoints once Souvik finishes the schema.
[Souvik]: I will design the new MongoDB schema migrations by Nov 25.
Manas: Assign Alex to set up the CI/CD pipeline by Nov 28.
Souvik: Someone needs to evaluate Redis caching.
"""
    segments = parse_transcript(transcript)
    speakers = [s.speaker for s in segments]
    assert 'Souvik' in speakers
    assert 'Manas' in speakers
    print("✓ test_multi_format_parsing passed")

    extracted = _smart_fallback_extraction(segments, "Database Architecture Sync", "2024-11-21")

    # Check decision
    assert len(extracted.decisions) >= 1
    d = extracted.decisions[0]
    assert d.decided_by == "Souvik"
    assert d.topic_key == "database"

    # Check action items
    owners = {a.owner: a for a in extracted.action_items}
    assert "Souvik" in owners, "Expected Souvik to own schema migrations"
    assert "Manas" in owners, "Expected Manas to own REST API endpoints"
    assert "Alex" in owners, "Expected Alex to own CI/CD pipeline via delegation"
    assert None in owners, "Expected unassigned Redis caching item with owner=None"

    # Check unassigned status
    unassigned = owners[None]
    assert unassigned.status == "NEEDS_CLARIFICATION"
    assert "owner" in unassigned.missing_fields

    # Check deadline
    souvik_task = owners["Souvik"]
    assert souvik_task.deadline_iso == "2024-11-25"

    alex_task = owners["Alex"]
    assert alex_task.deadline_iso == "2024-11-28"

    print("✓ test_extraction_and_owners passed")

def test_conflict_and_nudges():
    # Active decision in DB: Souvik chose PostgreSQL
    class MockMeeting:
        def __init__(self, title, meeting_date):
            self.title = title
            self.meeting_date = meeting_date

    class MockDecisionRecord:
        def __init__(self, id, topic_key, statement, decided_by, verbatim_quote=""):
            self.id = id
            self.topic_key = topic_key
            self.statement = statement
            self.decided_by = decided_by
            self.verbatim_quote = verbatim_quote

    old_dec = MockDecisionRecord(
        id=1,
        topic_key="database",
        statement="Use PostgreSQL 15 as our primary relational database.",
        decided_by="Souvik",
        verbatim_quote="Souvik: We are standardizing on PostgreSQL 15.",
    )
    old_meeting = MockMeeting("Architecture Kickoff", "2024-11-10")

    new_dec = LLMDecision(
        topic_key="database",
        statement="We are migrating from PostgreSQL to MongoDB.",
        decided_by="Manas",
        verbatim_quote="Manas: Let's switch to MongoDB.",
        confidence="HIGH"
    )

    conflict = _find_decision_conflict(new_dec, [(old_dec, old_meeting)])
    assert conflict is not None
    assert conflict.conflict_type == "CONFLICT"
    assert "Souvik" in conflict.conflict_explanation
    assert "Manas" in conflict.conflict_explanation
    print("Conflict explanation:", conflict.conflict_explanation)
    print("✓ test_conflict passed")

    # Nudge draft for unassigned item
    unassigned_nudge = generate_nudge_draft(
        item_payload={"title": "Evaluate Redis caching", "clarification_prompt": "Missing owner and deadline."},
        item_type="ACTION_ITEM",
        state="NEEDS_CLARIFICATION"
    )
    assert "@team" in unassigned_nudge
    print("Unassigned nudge:", unassigned_nudge)

    # Nudge draft for assigned task
    task_nudge = generate_nudge_draft(
        item_payload={"title": "Design MongoDB migrations", "owner": "Souvik", "deadline_iso": "2024-11-25"},
        item_type="TASK",
        state="STALE_TASK"
    )
    assert "@Souvik" in task_nudge
    print("Task nudge:", task_nudge)

    # Nudge draft for conflict item
    conflict_nudge = generate_nudge_draft(
        item_payload={"statement": "Switch from PostgreSQL to MongoDB", "decided_by": "Manas", "topic_key": "database"},
        item_type="DECISION",
        state="CONFLICT_DETECTED",
        conflict=conflict
    )
    assert "@Manas" in conflict_nudge
    assert "Architecture Kickoff" in conflict_nudge
    print("Conflict nudge:", conflict_nudge)
    print("✓ test_nudges passed")

if __name__ == "__main__":
    test_normalization()
    test_multi_format_parsing()
    test_conflict_and_nudges()
    print("\nALL VERIFICATIONS COMPLETED SUCCESSFULLY!")
