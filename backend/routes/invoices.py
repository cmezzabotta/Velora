from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, timedelta
import random
import string

from ..dependencies import get_db, get_current_user
from ..models import (
    Invoice,
    InvoiceItem,
    Order,
    OrderItem,
    Customer,
    Product,
    AccountMovement,
    InvoiceType as ModelInvoiceType,
    InvoiceStatus as ModelInvoiceStatus,
    AccountMovementType as ModelAccountMovementType,
)
from ..schemas import (
    InvoiceCreate,
    InvoiceResponse,
    InvoiceListItem,
    InvoiceType,
)

router = APIRouter(prefix="/invoices", tags=["Facturación"])


# ============================================================
# HELPERS
# ============================================================

def _formatted_number(point_of_sale: int, invoice_number: int) -> str:
    return f"{point_of_sale:04d}-{invoice_number:08d}"


def _next_invoice_number(db: Session, company_id: int, point_of_sale: int, invoice_type: str) -> int:
    last = (
        db.query(func.max(Invoice.invoice_number))
        .filter(
            Invoice.company_id == company_id,
            Invoice.point_of_sale == point_of_sale,
            Invoice.invoice_type == invoice_type,
        )
        .scalar()
    )
    return (last or 0) + 1


def _request_cae_stub():
    """
    PLACEHOLDER hasta integrar ARCA real (WSFEv1).
    """
    fake_cae = "TEST-" + "".join(random.choices(string.digits, k=12))
    due_date = datetime.utcnow() + timedelta(days=10)
    return fake_cae, due_date


def _get_invoice_or_404(invoice_id: int, db: Session, company_id: int) -> Invoice:
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.company_id == company_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    return invoice


def _get_customer_balance(db: Session, company_id: int, customer_id: int) -> Decimal:
    last = (
        db.query(AccountMovement)
        .filter(
            AccountMovement.company_id == company_id,
            AccountMovement.customer_id == customer_id,
        )
        .order_by(AccountMovement.id.desc())
        .first()
    )
    return last.balance_after if last else Decimal(0)


def _create_debit_for_invoice(db: Session, invoice: Invoice, customer: Customer) -> Optional[str]:
    """Toda factura autorizada genera una deuda en cuenta corriente.
    Devuelve un mensaje de aviso si supera el límite de crédito (no bloquea)."""
    current_balance = _get_customer_balance(db, invoice.company_id, invoice.customer_id)
    new_balance = current_balance + invoice.total

    db.add(AccountMovement(
        company_id=invoice.company_id,
        customer_id=invoice.customer_id,
        movement_type=ModelAccountMovementType.DEBITO,
        amount=invoice.total,
        invoice_id=invoice.id,
        description=f"Factura {_formatted_number(invoice.point_of_sale, invoice.invoice_number)}",
        balance_after=new_balance,
    ))

    if customer.credit_limit and new_balance > customer.credit_limit:
        return (
            f"El cliente supera su límite de crédito (${customer.credit_limit}). "
            f"Saldo actual: ${new_balance}."
        )
    return None


def _create_credit_for_note(db: Session, credit_note: Invoice, original: Invoice):
    """Una nota de crédito reduce la deuda del cliente."""
    current_balance = _get_customer_balance(db, credit_note.company_id, credit_note.customer_id)
    new_balance = current_balance - credit_note.total

    db.add(AccountMovement(
        company_id=credit_note.company_id,
        customer_id=credit_note.customer_id,
        movement_type=ModelAccountMovementType.CREDITO,
        amount=credit_note.total,
        invoice_id=credit_note.id,
        description=f"Nota de crédito por anulación de {_formatted_number(original.point_of_sale, original.invoice_number)}",
        balance_after=new_balance,
    ))


# ============================================================
# LISTAR
# ============================================================

@router.get("", response_model=List[InvoiceListItem])
def list_invoices(
    invoice_type: Optional[InvoiceType] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Invoice).filter(Invoice.company_id == current_user.company_id)

    if invoice_type:
        query = query.filter(Invoice.invoice_type == invoice_type)
    if date_from:
        query = query.filter(Invoice.issue_date >= date_from)
    if date_to:
        query = query.filter(Invoice.issue_date <= date_to)

    invoices = query.order_by(Invoice.issue_date.desc()).all()

    if not invoices:
        return []

    customer_ids = {inv.customer_id for inv in invoices}
    customers_map = {
        c.id: c.name
        for c in db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
    }

    return [
        InvoiceListItem(
            id=inv.id,
            customer_name=customers_map.get(inv.customer_id, "Cliente desconocido"),
            invoice_type=inv.invoice_type,
            formatted_number=_formatted_number(inv.point_of_sale, inv.invoice_number),
            issue_date=inv.issue_date,
            status=inv.status,
            total=inv.total,
        )
        for inv in invoices
    ]


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return _get_invoice_or_404(invoice_id, db, current_user.company_id)


# ============================================================
# CREAR (desde pedido o manual)
# ============================================================

@router.post("", response_model=InvoiceResponse)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company_id = current_user.company_id

    if payload.order_id:
        order = (
            db.query(Order)
            .filter(Order.id == payload.order_id, Order.company_id == company_id)
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        customer_id = order.customer_id
        order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        if not order_items:
            raise HTTPException(status_code=400, detail="El pedido no tiene productos")

        items_source = [
            {"product_id": item.product_id, "quantity": item.quantity, "unit_price": item.unit_price}
            for item in order_items
        ]
    else:
        if not payload.customer_id or not payload.items:
            raise HTTPException(
                status_code=400,
                detail="Una factura manual necesita customer_id e items",
            )
        customer_check = (
            db.query(Customer)
            .filter(Customer.id == payload.customer_id, Customer.company_id == company_id)
            .first()
        )
        if not customer_check:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")

        customer_id = payload.customer_id
        items_source = [
            {"product_id": item.product_id, "quantity": item.quantity, "unit_price": item.unit_price}
            for item in payload.items
        ]

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.company_id == company_id)
        .first()
    )

    invoice_number = _next_invoice_number(
        db, company_id, payload.point_of_sale, payload.invoice_type
    )

    invoice = Invoice(
        company_id=company_id,
        customer_id=customer_id,
        order_id=payload.order_id,
        invoice_type=payload.invoice_type,
        point_of_sale=payload.point_of_sale,
        invoice_number=invoice_number,
        payment_method=payload.payment_method,
        subtotal=0,
        tax_amount=0,
        total=0,
    )
    db.add(invoice)
    db.flush()

    subtotal_total = Decimal(0)
    tax_total = Decimal(0)

    for item_data in items_source:
        product = (
            db.query(Product)
            .filter(Product.id == item_data["product_id"], Product.company_id == company_id)
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Producto #{item_data['product_id']} no encontrado",
            )

        unit_price = item_data["unit_price"] if item_data.get("unit_price") is not None else product.price
        tax_rate = item_data.get("tax_rate") if item_data.get("tax_rate") is not None else product.tax_rate

        subtotal = unit_price * item_data["quantity"]
        tax_amount = subtotal * (Decimal(tax_rate) / Decimal(100))

        subtotal_total += subtotal
        tax_total += tax_amount

        db.add(InvoiceItem(
            invoice_id=invoice.id,
            product_id=item_data["product_id"],
            quantity=item_data["quantity"],
            unit_price=unit_price,
            tax_rate=tax_rate,
            subtotal=subtotal,
        ))

    invoice.subtotal = subtotal_total
    invoice.tax_amount = tax_total
    invoice.total = subtotal_total + tax_total

    cae, cae_due_date = _request_cae_stub()
    invoice.cae = cae
    invoice.cae_due_date = cae_due_date
    invoice.status = ModelInvoiceStatus.AUTORIZADA

    db.flush()

    credit_warning = _create_debit_for_invoice(db, invoice, customer)

    db.commit()
    db.refresh(invoice)

    response = InvoiceResponse.model_validate(invoice)
    response.credit_warning = credit_warning
    return response


# ============================================================
# ANULAR (genera Nota de Crédito, nunca edita/borra la original)
# ============================================================

@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
def cancel_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company_id = current_user.company_id
    original = _get_invoice_or_404(invoice_id, db, company_id)

    if original.status != ModelInvoiceStatus.AUTORIZADA:
        raise HTTPException(
            status_code=400,
            detail=f"Solo se puede anular una factura AUTORIZADA (estado actual: {original.status.value})",
        )
    if original.invoice_type in (ModelInvoiceType.NOTA_CREDITO, ModelInvoiceType.NOTA_DEBITO):
        raise HTTPException(status_code=400, detail="No se puede anular una nota de crédito/débito")

    original_items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == original.id).all()

    credit_number = _next_invoice_number(
        db, company_id, original.point_of_sale, ModelInvoiceType.NOTA_CREDITO
    )

    credit_note = Invoice(
        company_id=company_id,
        customer_id=original.customer_id,
        order_id=original.order_id,
        invoice_type=ModelInvoiceType.NOTA_CREDITO,
        point_of_sale=original.point_of_sale,
        invoice_number=credit_number,
        related_invoice_id=original.id,
        subtotal=original.subtotal,
        tax_amount=original.tax_amount,
        total=original.total,
        payment_method=original.payment_method,
    )
    db.add(credit_note)
    db.flush()

    for item in original_items:
        db.add(InvoiceItem(
            invoice_id=credit_note.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            tax_rate=item.tax_rate,
            subtotal=item.subtotal,
        ))

    cae, cae_due_date = _request_cae_stub()
    credit_note.cae = cae
    credit_note.cae_due_date = cae_due_date
    credit_note.status = ModelInvoiceStatus.AUTORIZADA

    original.status = ModelInvoiceStatus.ANULADA

    db.flush()

    _create_credit_for_note(db, credit_note, original)

    db.commit()
    db.refresh(credit_note)
    return credit_note