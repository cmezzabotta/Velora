from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..dependencies import get_db, get_current_user
from ..models import Supplier
from ..schemas import SupplierCreate, SupplierResponse

router = APIRouter(prefix="/suppliers", tags=["Proveedores"])


@router.get("", response_model=List[SupplierResponse])
def get_suppliers(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return (
        db.query(Supplier)
        .filter(
            Supplier.company_id == current_user.company_id,
            Supplier.active == True,
        )
        .order_by(Supplier.name.asc())
        .all()
    )


@router.post("", response_model=SupplierResponse)
def create_supplier(
    supplier: SupplierCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    new_supplier = Supplier(
        company_id=current_user.company_id,
        name=supplier.name,
        tax_id=supplier.tax_id,
        contact_name=supplier.contact_name,
        email=supplier.email,
        phone=supplier.phone,
        address=supplier.address,
        city=supplier.city,
        payment_terms=supplier.payment_terms,
        notes=supplier.notes,
        active=supplier.active,
    )
    db.add(new_supplier)
    db.commit()
    db.refresh(new_supplier)
    return new_supplier


@router.put("/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: int,
    supplier: SupplierCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    existing = (
        db.query(Supplier)
        .filter(
            Supplier.id == supplier_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    for field, value in supplier.model_dump().items():
        setattr(existing, field, value)

    db.commit()
    db.refresh(existing)
    return existing


@router.delete("/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    existing = (
        db.query(Supplier)
        .filter(
            Supplier.id == supplier_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    existing.active = False
    db.commit()
    return {"detail": "Proveedor desactivado"}