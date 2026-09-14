from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import Company
from ..schemas import CompanyResponse, CompanyCreate

router = APIRouter(prefix="/company", tags=["Configuración"])


@router.get("", response_model=CompanyResponse)
def get_company(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company = db.get(Company, current_user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return company


@router.put("", response_model=CompanyResponse)
def update_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company = db.get(Company, current_user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    for field, value in payload.model_dump().items():
        setattr(company, field, value)

    db.commit()
    db.refresh(company)
    return company