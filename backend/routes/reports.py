from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, timedelta

from ..dependencies import get_db, get_current_user
from ..models import (
    Invoice,
    InvoiceItem,
    Sale,
    Product,
    Customer,
    Supplier,
    Inventory,
    Warehouse,
    Purchase,
    AccountMovement,
    InvoiceStatus as ModelInvoiceStatus,
)

router = APIRouter(prefix="/reports", tags=["Reportes"])


def _default_range(date_from: Optional[datetime], date_to: Optional[datetime]):
    """Si no mandan fechas, default a los últimos 30 días."""
    if not date_to:
        date_to = datetime.utcnow()
    if not date_from:
        date_from = date_to - timedelta(days=30)
    return date_from, date_to


# ============================================================
# RESUMEN DE VENTAS (facturación + POS)
# ============================================================

@router.get("/sales-summary")
def sales_summary(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    date_from, date_to = _default_range(date_from, date_to)
    company_id = current_user.company_id

    invoices = (
        db.query(Invoice)
        .filter(
            Invoice.company_id == company_id,
            Invoice.status == ModelInvoiceStatus.AUTORIZADA,
            Invoice.invoice_type.in_(["A", "B", "C"]),
            Invoice.issue_date >= date_from,
            Invoice.issue_date <= date_to,
        )
        .all()
    )

    total_invoiced = sum((inv.total for inv in invoices), Decimal(0))

    by_type: dict = {"A": Decimal(0), "B": Decimal(0), "C": Decimal(0)}
    by_day: dict = {}
    for inv in invoices:
        by_type[inv.invoice_type.value] = by_type.get(inv.invoice_type.value, Decimal(0)) + inv.total
        day_key = inv.issue_date.date().isoformat()
        by_day[day_key] = by_day.get(day_key, Decimal(0)) + inv.total

    pos_sales = (
        db.query(Sale)
        .filter(
            Sale.company_id == company_id,
            Sale.status == "completed",
            Sale.created_at >= date_from,
            Sale.created_at <= date_to,
        )
        .all()
    )
    total_pos = sum((sale.total for sale in pos_sales), Decimal(0))

    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_invoiced": total_invoiced,
        "invoice_count": len(invoices),
        "total_pos": total_pos,
        "pos_count": len(pos_sales),
        "by_type": by_type,
        "by_day": [{"date": k, "total": v} for k, v in sorted(by_day.items())],
    }


# ============================================================
# PRODUCTOS MÁS VENDIDOS (según lo facturado)
# ============================================================

@router.get("/top-products")
def top_products(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    date_from, date_to = _default_range(date_from, date_to)
    company_id = current_user.company_id

    rows = (
        db.query(
            InvoiceItem.product_id,
            func.sum(InvoiceItem.quantity).label("quantity_sold"),
            func.sum(InvoiceItem.subtotal).label("revenue"),
        )
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .filter(
            Invoice.company_id == company_id,
            Invoice.status == ModelInvoiceStatus.AUTORIZADA,
            Invoice.invoice_type.in_(["A", "B", "C"]),
            Invoice.issue_date >= date_from,
            Invoice.issue_date <= date_to,
        )
        .group_by(InvoiceItem.product_id)
        .order_by(func.sum(InvoiceItem.quantity).desc())
        .limit(limit)
        .all()
    )

    product_ids = [r.product_id for r in rows]
    products_map = {
        p.id: p.name
        for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
    }

    return [
        {
            "product_id": r.product_id,
            "product_name": products_map.get(r.product_id, f"#{r.product_id}"),
            "quantity_sold": r.quantity_sold,
            "revenue": r.revenue,
        }
        for r in rows
    ]


# ============================================================
# CLIENTES QUE MÁS COMPRARON
# ============================================================

@router.get("/top-customers")
def top_customers(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    date_from, date_to = _default_range(date_from, date_to)
    company_id = current_user.company_id

    rows = (
        db.query(
            Invoice.customer_id,
            func.sum(Invoice.total).label("total_invoiced"),
            func.count(Invoice.id).label("invoice_count"),
        )
        .filter(
            Invoice.company_id == company_id,
            Invoice.status == ModelInvoiceStatus.AUTORIZADA,
            Invoice.invoice_type.in_(["A", "B", "C"]),
            Invoice.issue_date >= date_from,
            Invoice.issue_date <= date_to,
        )
        .group_by(Invoice.customer_id)
        .order_by(func.sum(Invoice.total).desc())
        .limit(limit)
        .all()
    )

    customer_ids = [r.customer_id for r in rows]
    customers_map = {
        c.id: c.name
        for c in db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
    }

    return [
        {
            "customer_id": r.customer_id,
            "customer_name": customers_map.get(r.customer_id, "Cliente desconocido"),
            "total_invoiced": r.total_invoiced,
            "invoice_count": r.invoice_count,
        }
        for r in rows
    ]


# ============================================================
# STOCK BAJO
# ============================================================

@router.get("/low-stock")
def low_stock(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company_id = current_user.company_id

    rows = (
        db.query(Inventory)
        .filter(
            Inventory.company_id == company_id,
            Inventory.min_stock.isnot(None),
            Inventory.quantity <= Inventory.min_stock,
        )
        .all()
    )

    product_ids = {r.product_id for r in rows}
    warehouse_ids = {r.warehouse_id for r in rows}
    products_map = {
        p.id: p.name for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
    }
    warehouses_map = {
        w.id: w.name for w in db.query(Warehouse).filter(Warehouse.id.in_(warehouse_ids)).all()
    }

    return [
        {
            "product_id": r.product_id,
            "product_name": products_map.get(r.product_id, f"#{r.product_id}"),
            "warehouse_name": warehouses_map.get(r.warehouse_id, f"#{r.warehouse_id}"),
            "quantity": r.quantity,
            "min_stock": r.min_stock,
        }
        for r in rows
    ]


# ============================================================
# CUENTAS POR COBRAR (clientes con saldo pendiente)
# ============================================================

@router.get("/accounts-receivable")
def accounts_receivable(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company_id = current_user.company_id

    customers = db.query(Customer).filter(Customer.company_id == company_id).all()

    result = []
    for customer in customers:
        last_movement = (
            db.query(AccountMovement)
            .filter(
                AccountMovement.company_id == company_id,
                AccountMovement.customer_id == customer.id,
            )
            .order_by(AccountMovement.id.desc())
            .first()
        )
        balance = last_movement.balance_after if last_movement else Decimal(0)
        if balance > 0:
            result.append({
                "customer_id": customer.id,
                "customer_name": customer.name,
                "balance": balance,
                "credit_limit": customer.credit_limit,
            })

    result.sort(key=lambda x: x["balance"], reverse=True)
    return result


# ============================================================
# RESUMEN DE COMPRAS
# ============================================================

@router.get("/purchases-summary")
def purchases_summary(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    date_from, date_to = _default_range(date_from, date_to)
    company_id = current_user.company_id

    rows = (
        db.query(
            Purchase.supplier_id,
            func.sum(Purchase.total).label("total"),
            func.count(Purchase.id).label("purchase_count"),
        )
        .filter(
            Purchase.company_id == company_id,
            Purchase.status == "RECIBIDA",
            Purchase.created_at >= date_from,
            Purchase.created_at <= date_to,
        )
        .group_by(Purchase.supplier_id)
        .order_by(func.sum(Purchase.total).desc())
        .all()
    )

    supplier_ids = [r.supplier_id for r in rows]
    suppliers_map = {
        s.id: s.name for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
    }

    total = sum((r.total for r in rows), Decimal(0))

    return {
        "total": total,
        "by_supplier": [
            {
                "supplier_id": r.supplier_id,
                "supplier_name": suppliers_map.get(r.supplier_id, f"#{r.supplier_id}"),
                "total": r.total,
                "purchase_count": r.purchase_count,
            }
            for r in rows
        ],
    }