from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from decimal import Decimal

from ..dependencies import get_db, get_current_user
from ..models import (
    Sale,
    SaleItem,
    Product,
    Customer,
    Inventory,
    StockMovement,
    MovementType,
    CashSession,
    CashSessionStatus as ModelCashSessionStatus,
)
from ..schemas import SaleCreate, SaleResponse, SaleListItem

router = APIRouter(prefix="/pos", tags=["POS"])


def _items_summary(items: List[SaleItem], products_map: dict) -> str:
    names = [products_map.get(item.product_id, f"#{item.product_id}") for item in items]
    if len(names) <= 2:
        return ", ".join(names)
    return f"{names[0]}, {names[1]} y {len(names) - 2} más"


@router.post("/sale", response_model=SaleResponse)
def create_sale(
    payload: SaleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company_id = current_user.company_id

    # Necesita una caja abierta para vender
    session = (
        db.query(CashSession)
        .filter(
            CashSession.company_id == company_id,
            CashSession.status == ModelCashSessionStatus.ABIERTA,
        )
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=400,
            detail="No hay una caja abierta. Abrí la caja antes de vender.",
        )

    if payload.customer_id:
        customer = (
            db.query(Customer)
            .filter(Customer.id == payload.customer_id, Customer.company_id == company_id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if not payload.items:
        raise HTTPException(status_code=400, detail="La venta necesita al menos un producto")

    # -------------------------------------------------
    # Validar stock disponible ANTES de tocar nada
    # -------------------------------------------------
    inventories = {}
    for item in payload.items:
        inv = (
            db.query(Inventory)
            .filter(
                Inventory.company_id == company_id,
                Inventory.warehouse_id == payload.warehouse_id,
                Inventory.product_id == item.product_id,
            )
            .first()
        )
        available = (inv.quantity - inv.reserved_quantity) if inv else Decimal(0)
        if item.quantity > available:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente para el producto #{item.product_id}. "
                       f"Disponible: {available}",
            )
        inventories[item.product_id] = inv

    # -------------------------------------------------
    # Crear la venta
    # -------------------------------------------------
    sale = Sale(
        company_id=company_id,
        customer_id=payload.customer_id,
        warehouse_id=payload.warehouse_id,
        cash_session_id=session.id,
        payment_method=payload.payment_method,
        status="completed",
        subtotal=0,
        tax_amount=0,
        total=0,
    )
    db.add(sale)
    db.flush()

    subtotal_total = Decimal(0)
    tax_total = Decimal(0)

    for item in payload.items:
        product = (
            db.query(Product)
            .filter(Product.id == item.product_id, Product.company_id == company_id)
            .first()
        )
        if not product:
            raise HTTPException(status_code=404, detail=f"Producto #{item.product_id} no encontrado")

        unit_price = item.unit_price if item.unit_price is not None else product.price
        tax_rate = product.tax_rate
        subtotal = unit_price * item.quantity
        tax_amount = subtotal * (Decimal(tax_rate) / Decimal(100))

        subtotal_total += subtotal
        tax_total += tax_amount

        db.add(SaleItem(
            sale_id=sale.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=unit_price,
            tax_rate=tax_rate,
            subtotal=subtotal,
        ))

        # Descuento inmediato de stock físico (venta de mostrador, sin reserva previa)
        inv = inventories[item.product_id]
        previous_qty = inv.quantity
        inv.quantity = inv.quantity - item.quantity

        db.add(StockMovement(
            company_id=company_id,
            warehouse_id=payload.warehouse_id,
            product_id=item.product_id,
            user_id=current_user.id,
            movement_type=MovementType.SALIDA,
            quantity=item.quantity,
            previous_qty=previous_qty,
            new_qty=inv.quantity,
            reference=f"Venta POS #{sale.id}",
        ))

    sale.subtotal = subtotal_total
    sale.tax_amount = tax_total
    sale.total = subtotal_total + tax_total

    db.commit()
    db.refresh(sale)
    return sale


@router.get("/sales", response_model=List[SaleListItem])
def list_sales(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    sales = (
        db.query(Sale)
        .filter(Sale.company_id == current_user.company_id)
        .order_by(Sale.created_at.desc())
        .limit(200)
        .all()
    )
    if not sales:
        return []

    customer_ids = {s.customer_id for s in sales if s.customer_id}
    customers_map = {
        c.id: c.name
        for c in db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
    }

    sale_ids = [s.id for s in sales]
    all_items = db.query(SaleItem).filter(SaleItem.sale_id.in_(sale_ids)).all()
    items_by_sale = {}
    for item in all_items:
        items_by_sale.setdefault(item.sale_id, []).append(item)

    product_ids = {item.product_id for item in all_items}
    products_map = {
        p.id: p.name
        for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
    }

    return [
        SaleListItem(
            id=sale.id,
            customer_name=customers_map.get(sale.customer_id, "Consumidor final"),
            items_summary=_items_summary(items_by_sale.get(sale.id, []), products_map),
            total=sale.total,
            payment_method=sale.payment_method,
            created_at=sale.created_at,
        )
        for sale in sales
    ]