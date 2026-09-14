from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

from ..dependencies import get_db, get_current_user
from ..models import (
    Purchase,
    PurchaseItem,
    Supplier,
    Product,
    Inventory,
    StockMovement,
    MovementType,
    PurchaseStatus as ModelPurchaseStatus,
)
from ..schemas import (
    PurchaseCreate,
    PurchaseResponse,
    PurchaseListItem,
    PurchaseStatus,
)

router = APIRouter(prefix="/purchases", tags=["Compras"])


# ============================================================
# HELPERS
# ============================================================

def _get_purchase_or_404(purchase_id: int, db: Session, company_id: int) -> Purchase:
    purchase = (
        db.query(Purchase)
        .filter(Purchase.id == purchase_id, Purchase.company_id == company_id)
        .first()
    )
    if not purchase:
        raise HTTPException(status_code=404, detail="Compra no encontrada")
    return purchase


def _items_summary(items: List[PurchaseItem], products_map: dict) -> str:
    names = [products_map.get(item.product_id, f"#{item.product_id}") for item in items]
    if len(names) <= 2:
        return ", ".join(names)
    return f"{names[0]}, {names[1]} y {len(names) - 2} más"


# ============================================================
# LISTAR
# ============================================================

@router.get("", response_model=List[PurchaseListItem])
def list_purchases(
    status: Optional[PurchaseStatus] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Purchase).filter(Purchase.company_id == current_user.company_id)
    if status:
        query = query.filter(Purchase.status == status)

    purchases = query.order_by(Purchase.created_at.desc()).all()
    if not purchases:
        return []

    supplier_ids = {p.supplier_id for p in purchases}
    suppliers_map = {
        s.id: s.name
        for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
    }

    purchase_ids = [p.id for p in purchases]
    all_items = (
        db.query(PurchaseItem).filter(PurchaseItem.purchase_id.in_(purchase_ids)).all()
    )
    items_by_purchase = {}
    for item in all_items:
        items_by_purchase.setdefault(item.purchase_id, []).append(item)

    product_ids = {item.product_id for item in all_items}
    products_map = {
        p.id: p.name
        for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
    }

    return [
        PurchaseListItem(
            id=purchase.id,
            supplier_name=suppliers_map.get(purchase.supplier_id, "Proveedor desconocido"),
            status=purchase.status,
            items_summary=_items_summary(items_by_purchase.get(purchase.id, []), products_map),
            total=purchase.total,
            created_at=purchase.created_at,
        )
        for purchase in purchases
    ]


@router.get("/{purchase_id}", response_model=PurchaseResponse)
def get_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return _get_purchase_or_404(purchase_id, db, current_user.company_id)


# ============================================================
# CREAR
# ============================================================

@router.post("", response_model=PurchaseResponse)
def create_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company_id = current_user.company_id

    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == payload.supplier_id, Supplier.company_id == company_id)
        .first()
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    if not payload.items:
        raise HTTPException(status_code=400, detail="La compra necesita al menos un producto")

    purchase = Purchase(
        company_id=company_id,
        supplier_id=payload.supplier_id,
        warehouse_id=payload.warehouse_id,
        supplier_invoice_number=payload.supplier_invoice_number,
        notes=payload.notes,
        status=ModelPurchaseStatus.PENDIENTE,
        subtotal=0,
        total=0,
    )
    db.add(purchase)
    db.flush()

    total = Decimal(0)
    for item_payload in payload.items:
        product = (
            db.query(Product)
            .filter(Product.id == item_payload.product_id, Product.company_id == company_id)
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Producto #{item_payload.product_id} no encontrado",
            )

        subtotal = item_payload.unit_cost * item_payload.quantity
        total += subtotal

        db.add(PurchaseItem(
            purchase_id=purchase.id,
            product_id=item_payload.product_id,
            quantity=item_payload.quantity,
            unit_cost=item_payload.unit_cost,
            subtotal=subtotal,
        ))

    purchase.subtotal = total
    purchase.total = total

    db.commit()
    db.refresh(purchase)
    return purchase


# ============================================================
# RECIBIR (genera ENTRADA de stock por cada item)
# ============================================================

@router.post("/{purchase_id}/receive", response_model=PurchaseResponse)
def receive_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    purchase = _get_purchase_or_404(purchase_id, db, current_user.company_id)

    if purchase.status != ModelPurchaseStatus.PENDIENTE:
        raise HTTPException(
            status_code=400,
            detail=f"Solo se puede recibir una compra PENDIENTE (estado actual: {purchase.status.value})",
        )

    items = db.query(PurchaseItem).filter(PurchaseItem.purchase_id == purchase.id).all()

    for item in items:
        inv = (
            db.query(Inventory)
            .filter(
                Inventory.company_id == purchase.company_id,
                Inventory.warehouse_id == purchase.warehouse_id,
                Inventory.product_id == item.product_id,
            )
            .first()
        )

        if not inv:
            inv = Inventory(
                company_id=purchase.company_id,
                warehouse_id=purchase.warehouse_id,
                product_id=item.product_id,
                quantity=0,
                reserved_quantity=0,
            )
            db.add(inv)
            db.flush()

        previous_qty = inv.quantity
        inv.quantity = inv.quantity + item.quantity

        db.add(StockMovement(
            company_id=purchase.company_id,
            warehouse_id=purchase.warehouse_id,
            product_id=item.product_id,
            user_id=current_user.id,
            movement_type=MovementType.ENTRADA,
            quantity=item.quantity,
            previous_qty=previous_qty,
            new_qty=inv.quantity,
            reference=f"Compra #{purchase.id}",
        ))

    purchase.status = ModelPurchaseStatus.RECIBIDA
    purchase.received_at = datetime.utcnow()

    db.commit()
    db.refresh(purchase)
    return purchase


# ============================================================
# CANCELAR (solo si todavía no se recibió)
# ============================================================

@router.post("/{purchase_id}/cancel", response_model=PurchaseResponse)
def cancel_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    purchase = _get_purchase_or_404(purchase_id, db, current_user.company_id)

    if purchase.status != ModelPurchaseStatus.PENDIENTE:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede cancelar una compra PENDIENTE. "
                   "Si ya fue recibida, el stock ya se actualizó y no se puede deshacer desde acá.",
        )

    purchase.status = ModelPurchaseStatus.CANCELADA

    db.commit()
    db.refresh(purchase)
    return purchase