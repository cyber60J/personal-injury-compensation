from __future__ import annotations

from sqlalchemy.orm import Session

from personal_injury.domain.guidance import SOURCE_REFERENCES
from personal_injury.infrastructure.database import LegalSourceModel


def seed_legal_sources(session: Session) -> int:
    """Register known official sources without marking them as lawyer verified."""
    added = 0
    for source_key, reference in SOURCE_REFERENCES.items():
        if session.query(LegalSourceModel).filter(LegalSourceModel.source_key == source_key).first():
            continue
        session.add(
            LegalSourceModel(
                source_key=source_key,
                title=reference["title"],
                url=reference["url"],
                source_type="official",
                verification_status="pending",
                notes=reference.get("takeaway"),
            )
        )
        added += 1
    if added:
        session.commit()
    return added
