"""Create fictional subjects for demonstrating the investigation dashboard."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from models.subject import SubjectCreateRequest, SubjectStatus, SubjectType  # noqa: E402
from subject_manager import get_subject_manager  # noqa: E402


EXAMPLES = [
    SubjectCreateRequest(
        name="[Example] Northstar Research Lab",
        subject_type=SubjectType.ORGANIZATION,
        canonical_identifier="northstar-lab.example",
        aliases=["Northstar Lab", "NSRL"],
        identifiers=["example-org-001"],
        description="Fictional research organization used to demonstrate a company or organization investigation.",
        investigation_goals="Map public leadership, related domains, and reported partnerships.",
    ),
    SubjectCreateRequest(
        name="[Example] Aurora Signal",
        subject_type=SubjectType.DOMAIN,
        canonical_identifier="aurora-signal.example",
        aliases=["Aurora Signal site"],
        identifiers=["example-domain-002"],
        description="Fictional domain used to demonstrate an active technical investigation.",
        investigation_goals="Identify ownership signals, infrastructure relationships, and historical changes.",
    ),
    SubjectCreateRequest(
        name="[Example] Project Meridian",
        subject_type=SubjectType.EVENT,
        canonical_identifier="meridian-brief.example",
        aliases=["Meridian briefing"],
        identifiers=["example-event-003"],
        description="Fictional completed investigation used to demonstrate the completed-subject area.",
        investigation_goals="Review public chronology and archive the completed findings.",
        status=SubjectStatus.DONE,
    ),
]


def main() -> None:
    manager = get_subject_manager()
    existing_names = {subject.name for subject in manager.list()}
    created = 0
    for request in EXAMPLES:
        if request.name in existing_names:
            continue
        manager.create(request)
        created += 1
    print(f"Created {created} example subject(s).")


if __name__ == "__main__":
    main()
