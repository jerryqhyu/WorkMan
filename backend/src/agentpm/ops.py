from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Operation


def record_operation(
    session: Session,
    *,
    project_id: str,
    entity_type: str,
    entity_id: str,
    op_type: str,
    payload: dict,
) -> None:
    session.add(
        Operation(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            op_type=op_type,
            payload=payload,
        )
    )
