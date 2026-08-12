"""JSON-backed persistence for investigation subjects."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from models.subject import Subject, SubjectCreateRequest, SubjectUpdateRequest


class SubjectManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.subjects_dir = data_dir / "subjects"
        self.subjects_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, subject_id: str) -> Path:
        return self.subjects_dir / f"{subject_id}.json"

    def create(self, request: SubjectCreateRequest) -> Subject:
        subject = Subject(
            subject_id=f"SUB-{uuid.uuid4().hex[:10].upper()}",
            **request.dict(),
        )
        self._save(subject)
        return subject

    def get(self, subject_id: str) -> Subject | None:
        path = self._path(subject_id)
        if not path.exists():
            return None
        try:
            return Subject(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def list(self) -> list[Subject]:
        subjects = []
        for path in self.subjects_dir.glob("*.json"):
            subject = self.get(path.stem)
            if subject:
                # Keep dashboard counts tied to persisted thread transcripts.
                # Empty subject-thread records are created by the API before
                # the first message, so valid new threads are retained here.
                existing_ids = {
                    thread_path.stem
                    for thread_path in (self.data_dir / "threads").glob("*.json")
                }
                valid_thread_ids = [thread_id for thread_id in subject.thread_ids if thread_id in existing_ids]
                if valid_thread_ids != subject.thread_ids:
                    subject.thread_ids = valid_thread_ids
                    self._save(subject)
                subjects.append(subject)
        return sorted(subjects, key=lambda s: s.updated_at, reverse=True)

    def update(self, subject_id: str, request: SubjectUpdateRequest) -> Subject | None:
        subject = self.get(subject_id)
        if not subject:
            return None
        for key, value in request.dict(exclude_unset=True).items():
            setattr(subject, key, value)
        subject.updated_at = datetime.utcnow()
        self._save(subject)
        return subject

    def delete(self, subject_id: str) -> bool:
        path = self._path(subject_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def add_thread(self, subject_id: str, thread_id: str) -> Subject | None:
        subject = self.get(subject_id)
        if not subject:
            return None
        if thread_id not in subject.thread_ids:
            subject.thread_ids.append(thread_id)
            subject.updated_at = datetime.utcnow()
            self._save(subject)
        return subject

    def get_by_thread(self, thread_id: str) -> Subject | None:
        for subject in self.list():
            if thread_id in subject.thread_ids:
                return subject
        return None

    def _save(self, subject: Subject) -> None:
        self._path(subject.subject_id).write_text(
            json.dumps(subject.dict(), indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )


_MANAGER: SubjectManager | None = None


def get_subject_manager() -> SubjectManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = SubjectManager(Path(__file__).parent / "data")
    return _MANAGER
