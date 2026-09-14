from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from decimal import Decimal

from ..dependencies import get_db, get_current_user
from ..models import (
    CashSession,
    CashMovement,
    Sale,
    CashSessionStatus as ModelCashSessionStatus,
    CashMovementType as ModelCashMovementType,
)
from ..schemas import (
    CashSessionOpen,
    CashSessionClose,
    CashMovementCreate,
    CashSessionResponse,
)

router = APIRouter(prefix="/cash-sessions", tags=["Caja"])


def _get_session_or_404(session_id: int, db: Session, company_id: int) -> CashSession:
    session = (
        db.query(CashSession)
        .filter(CashSession.id == session_id, CashSession.company_id == company_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sesión de caja no encontrada")
    return session


@router.get("/current", response_model=CashSessionResponse)
def get_current_session(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = (
        db.query(CashSession)
        .filter(
            CashSession.company_id == current_user.company_id,
            CashSession.status == ModelCashSessionStatus.ABIERTA,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="No hay una caja abierta")
    return session


@router.get("", response_model=List[CashSessionResponse])
def list_sessions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return (
        db.query(CashSession)
        .filter(CashSession.company_id == current_user.company_id)
        .order_by(CashSession.opening_at.desc())
        .all()
    )


@router.post("", response_model=CashSessionResponse)
def open_session(
    payload: CashSessionOpen,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    existing = (
        db.query(CashSession)
        .filter(
            CashSession.company_id == current_user.company_id,
            CashSession.status == ModelCashSessionStatus.ABIERTA,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Ya hay una caja abierta")

    session = CashSession(
        company_id=current_user.company_id,
        user_id=current_user.id,
        opening_amount=payload.opening_amount,
        notes=payload.notes,
        status=ModelCashSessionStatus.ABIERTA,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/movements", response_model=CashSessionResponse)
def add_movement(
    session_id: int,
    payload: CashMovementCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = _get_session_or_404(session_id, db, current_user.company_id)

    if session.status != ModelCashSessionStatus.ABIERTA:
        raise HTTPException(status_code=400, detail="La caja ya está cerrada")

    db.add(CashMovement(
        company_id=current_user.company_id,
        cash_session_id=session.id,
        movement_type=payload.movement_type,
        amount=payload.amount,
        description=payload.description,
    ))

    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/close", response_model=CashSessionResponse)
def close_session(
    session_id: int,
    payload: CashSessionClose,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = _get_session_or_404(session_id, db, current_user.company_id)

    if session.status != ModelCashSessionStatus.ABIERTA:
        raise HTTPException(status_code=400, detail="Esta caja ya está cerrada")

    cash_sales_total = (
        db.query(Sale)
        .filter(
            Sale.cash_session_id == session.id,
            Sale.payment_method == "EFECTIVO",
            Sale.status == "completed",
        )
        .all()
    )
    sales_amount = sum((sale.total for sale in cash_sales_total), Decimal(0))

    movements = (
        db.query(CashMovement)
        .filter(CashMovement.cash_session_id == session.id)
        .all()
    )
    ingresos = sum(
        (m.amount for m in movements if m.movement_type == ModelCashMovementType.INGRESO),
        Decimal(0),
    )
    egresos = sum(
        (m.amount for m in movements if m.movement_type == ModelCashMovementType.EGRESO),
        Decimal(0),
    )

    expected = session.opening_amount + sales_amount + ingresos - egresos

    session.expected_amount = expected
    session.closing_amount = payload.closing_amount
    session.difference = payload.closing_amount - expected
    session.notes = payload.notes or session.notes
    session.status = ModelCashSessionStatus.CERRADA

    from datetime import datetime
    session.closing_at = datetime.utcnow()

    db.commit()
    db.refresh(session)
    return session