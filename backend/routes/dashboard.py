from datetime import datetime, time
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import (
    Product,
    Order,
    Sale,
    Invoice,
    Payment,
    Purchase,
    Customer,
    Inventory,
    AccountMovement,
    CashSession,
    User,
    OrderStatus as ModelOrderStatus,
    InvoiceStatus as ModelInvoiceStatus,
    PurchaseStatus as ModelPurchaseStatus,
    CashSessionStatus as ModelCashSessionStatus,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_id = current_user.company_id

    # =========================
    # PRODUCTOS ACTIVOS
    # =========================
    products_count = (
        db.query(func.count(Product.id))
        .filter(Product.company_id == company_id, Product.active == True)
        .scalar()
    )

    # =========================
    # VENTAS DE HOY (facturado + POS)
    # =========================
    today = datetime.now().date()
    start_of_day = datetime.combine(today, time.min)
    end_of_day = datetime.combine(today, time.max)

    invoiced_today = (
        db.query(func.coalesce(func.sum(Invoice.total), 0))
        .filter(
            Invoice.company_id == company_id,
            Invoice.status == ModelInvoiceStatus.AUTORIZADA,
            Invoice.invoice_type.in_(["A", "B", "C"]),
            Invoice.issue_date >= start_of_day,
            Invoice.issue_date <= end_of_day,
        )
        .scalar()
    )

    pos_today = (
        db.query(func.coalesce(func.sum(Sale.total), 0))
        .filter(
            Sale.company_id == company_id,
            Sale.status == "completed",
            Sale.created_at >= start_of_day,
            Sale.created_at <= end_of_day,
        )
        .scalar()
    )

    # =========================
    # PEDIDOS Y ENTREGAS PENDIENTES
    # =========================
    pending_orders = (
        db.query(func.count(Order.id))
        .filter(
            Order.company_id == company_id,
            Order.status.in_(["PENDIENTE", "CONFIRMADO", "PROGRAMADO", "EN_CAMINO"]),
        )
        .scalar()
    )

    pending_deliveries = (
        db.query(func.count(Order.id))
        .filter(
            Order.company_id == company_id,
            Order.delivery_type == "ENVIO",
            Order.status.in_(["PROGRAMADO", "EN_CAMINO"]),
        )
        .scalar()
    )

    # =========================
    # STOCK BAJO
    # =========================
    low_stock_count = (
        db.query(func.count(Inventory.id))
        .filter(
            Inventory.company_id == company_id,
            Inventory.min_stock.isnot(None),
            Inventory.quantity <= Inventory.min_stock,
        )
        .scalar()
    )

    # =========================
    # CUENTAS POR COBRAR (suma de saldos positivos)
    # =========================
    customers = db.query(Customer).filter(Customer.company_id == company_id).all()
    receivable_total = Decimal(0)
    for customer in customers:
        last_mov = (
            db.query(AccountMovement)
            .filter(
                AccountMovement.company_id == company_id,
                AccountMovement.customer_id == customer.id,
            )
            .order_by(AccountMovement.id.desc())
            .first()
        )
        balance = last_mov.balance_after if last_mov else Decimal(0)
        if balance > 0:
            receivable_total += balance

    # =========================
    # ESTADO DE CAJA
    # =========================
    open_session = (
        db.query(CashSession)
        .filter(
            CashSession.company_id == company_id,
            CashSession.status == ModelCashSessionStatus.ABIERTA,
        )
        .first()
    )

    cash_session_open = open_session is not None
    cash_session_info = None
    if open_session:
        cash_sales = (
            db.query(func.coalesce(func.sum(Sale.total), 0))
            .filter(
                Sale.cash_session_id == open_session.id,
                Sale.payment_method == "EFECTIVO",
                Sale.status == "completed",
            )
            .scalar()
        )
        cash_session_info = {
            "opening_amount": open_session.opening_amount,
            "opening_at": open_session.opening_at,
            "cash_sales_so_far": cash_sales,
        }

    # =========================
    # COMPRAS PENDIENTES DE RECIBIR
    # =========================
    pending_purchases = (
        db.query(func.count(Purchase.id))
        .filter(
            Purchase.company_id == company_id,
            Purchase.status == ModelPurchaseStatus.PENDIENTE,
        )
        .scalar()
    )

    return {
        "products": products_count or 0,
        "sales_today": float((invoiced_today or 0) + (pos_today or 0)),
        "invoiced_today": float(invoiced_today or 0),
        "pos_today": float(pos_today or 0),
        "pending_orders": pending_orders or 0,
        "pending_deliveries": pending_deliveries or 0,
        "low_stock_count": low_stock_count or 0,
        "accounts_receivable": float(receivable_total),
        "pending_purchases": pending_purchases or 0,
        "cash_session_open": cash_session_open,
        "cash_session": cash_session_info,
    }


@router.get("/activity")
def get_dashboard_activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_id = current_user.company_id
    activity = []

    # Pedidos recientes
    orders = (
        db.query(Order)
        .filter(Order.company_id == company_id)
        .order_by(Order.created_at.desc())
        .limit(5)
        .all()
    )
    customer_ids = {o.customer_id for o in orders}
    customers_map = {
        c.id: c.name
        for c in db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
    } if customer_ids else {}

    for order in orders:
        activity.append({
            "type": "order",
            "title": "Nuevo pedido",
            "description": customers_map.get(order.customer_id, "Cliente desconocido"),
            "status": order.status,
            "created_at": order.created_at,
        })

    # Facturas recientes
    invoices = (
        db.query(Invoice)
        .filter(Invoice.company_id == company_id)
        .order_by(Invoice.created_at.desc())
        .limit(5)
        .all()
    )
    for invoice in invoices:
        activity.append({
            "type": "invoice",
            "title": f"Factura {invoice.invoice_type.value}" if invoice.invoice_type else "Factura",
            "description": f"${float(invoice.total):,.0f}",
            "status": invoice.status,
            "created_at": invoice.created_at,
        })

    # Pagos recientes
    payments = (
        db.query(Payment)
        .filter(Payment.company_id == company_id)
        .order_by(Payment.created_at.desc())
        .limit(5)
        .all()
    )
    for payment in payments:
        activity.append({
            "type": "payment",
            "title": "Pago recibido",
            "description": f"${float(payment.amount):,.0f}",
            "status": "completed",
            "created_at": payment.created_at,
        })

    # Ventas POS recientes
    sales = (
        db.query(Sale)
        .filter(Sale.company_id == company_id)
        .order_by(Sale.created_at.desc())
        .limit(5)
        .all()
    )
    for sale in sales:
        activity.append({
            "type": "sale",
            "title": "Venta POS",
            "description": f"${float(sale.total):,.0f}",
            "status": sale.status,
            "created_at": sale.created_at,
        })

    # Compras recientes
    purchases = (
        db.query(Purchase)
        .filter(Purchase.company_id == company_id)
        .order_by(Purchase.created_at.desc())
        .limit(5)
        .all()
    )
    for purchase in purchases:
        activity.append({
            "type": "purchase",
            "title": "Compra registrada",
            "description": f"${float(purchase.total):,.0f}",
            "status": purchase.status,
            "created_at": purchase.created_at,
        })

    activity.sort(key=lambda item: item["created_at"], reverse=True)
    return activity[:10]