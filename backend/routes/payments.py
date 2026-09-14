from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal

from ..dependencies import get_db, get_current_user
from ..models import (
    Payment,
    PaymentApplication,
    Invoice,
    Customer,
    AccountMovement,
    AccountMovementType as ModelAccountMovementType,
    InvoiceStatus as ModelInvoiceStatus,
)
from ..schemas import (
    PaymentCreate,
    PaymentResponse,
    AccountStatement,
    AccountMovementResponse,
    OpenInvoiceItem,
)

payments_router = APIRouter(prefix="/payments", tags=["Pagos"])
accounts_router = APIRouter(prefix="/accounts", tags=["Cuentas Corrientes"])


# ============================================================
# HELPERS
# ============================================================

def _formatted_number(point_of_sale: int, invoice_number: int) -> str:
    return f"{point_of_sale:04d}-{invoice_number:08d}"


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


def _invoice_paid_amount(db: Session, invoice_id: int) -> Decimal:
    applications = (
        db.query(PaymentApplication)
        .filter(PaymentApplication.invoice_id == invoice_id)
        .all()
    )
    return sum((app.amount_applied for app in applications), Decimal(0))


# ============================================================
# REGISTRAR PAGO
# ============================================================

@payments_router.post("", response_model=PaymentResponse)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company_id = current_user.company_id

    customer = (
        db.query(Customer)
        .filter(Customer.id == payload.customer_id, Customer.company_id == company_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    # -------------------------------------------------
    # Validar aplicaciones a facturas (si se especificaron)
    # -------------------------------------------------
    applications_data = payload.applications or []
    total_applied = sum((app.amount_applied for app in applications_data), Decimal(0))

    if total_applied > payload.amount:
        raise HTTPException(
            status_code=400,
            detail="La suma de lo aplicado a facturas no puede superar el monto del pago",
        )

    for app in applications_data:
        invoice = (
            db.query(Invoice)
            .filter(
                Invoice.id == app.invoice_id,
                Invoice.company_id == company_id,
                Invoice.customer_id == payload.customer_id,
            )
            .first()
        )
        if not invoice:
            raise HTTPException(
                status_code=404,
                detail=f"Factura #{app.invoice_id} no encontrada para este cliente",
            )
        if invoice.status != ModelInvoiceStatus.AUTORIZADA:
            raise HTTPException(
                status_code=400,
                detail=f"La factura {_formatted_number(invoice.point_of_sale, invoice.invoice_number)} "
                       f"no está AUTORIZADA",
            )

        pending = invoice.total - _invoice_paid_amount(db, invoice.id)
        if app.amount_applied > pending:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede aplicar ${app.amount_applied} a la factura "
                       f"{_formatted_number(invoice.point_of_sale, invoice.invoice_number)}, "
                       f"su saldo pendiente es ${pending}",
            )

    # -------------------------------------------------
    # Crear el pago
    # -------------------------------------------------
    payment = Payment(
        company_id=company_id,
        customer_id=payload.customer_id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        payment_date=payload.payment_date,
        notes=payload.notes,
    )
    db.add(payment)
    db.flush()

    for app in applications_data:
        db.add(PaymentApplication(
            payment_id=payment.id,
            invoice_id=app.invoice_id,
            amount_applied=app.amount_applied,
        ))

    # -------------------------------------------------
    # Movimiento de cuenta corriente: CREDITO por el total pagado
    # (aunque no esté 100% aplicado a facturas puntuales, reduce
    # la deuda general del cliente)
    # -------------------------------------------------
    current_balance = _get_customer_balance(db, company_id, payload.customer_id)
    new_balance = current_balance - payload.amount

    description = "Pago recibido"
    if applications_data:
        numbers = []
        for app in applications_data:
            inv = db.query(Invoice).filter(Invoice.id == app.invoice_id).first()
            if inv:
                numbers.append(_formatted_number(inv.point_of_sale, inv.invoice_number))
        if numbers:
            description = f"Pago aplicado a: {', '.join(numbers)}"

    db.add(AccountMovement(
        company_id=company_id,
        customer_id=payload.customer_id,
        movement_type=ModelAccountMovementType.CREDITO,
        amount=payload.amount,
        payment_id=payment.id,
        description=description,
        balance_after=new_balance,
    ))

    db.commit()
    db.refresh(payment)
    return payment


# ============================================================
# LISTAR PAGOS
# ============================================================

@payments_router.get("", response_model=List[PaymentResponse])
def list_payments(
    customer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Payment).filter(Payment.company_id == current_user.company_id)
    if customer_id:
        query = query.filter(Payment.customer_id == customer_id)

    return query.order_by(Payment.payment_date.desc()).all()


# ============================================================
# ESTADO DE CUENTA
# ============================================================

@accounts_router.get("/{customer_id}", response_model=AccountStatement)
def get_account_statement(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    company_id = current_user.company_id

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.company_id == company_id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    balance = _get_customer_balance(db, company_id, customer_id)
    available = customer.credit_limit - balance if customer.credit_limit else Decimal(0)

    movements = (
        db.query(AccountMovement)
        .filter(
            AccountMovement.company_id == company_id,
            AccountMovement.customer_id == customer_id,
        )
        .order_by(AccountMovement.created_at.desc())
        .all()
    )

    invoices = (
        db.query(Invoice)
        .filter(
            Invoice.company_id == company_id,
            Invoice.customer_id == customer_id,
            Invoice.status == ModelInvoiceStatus.AUTORIZADA,
            Invoice.invoice_type.in_(["A", "B", "C"]),
        )
        .all()
    )

    open_invoices = []
    for invoice in invoices:
        paid = _invoice_paid_amount(db, invoice.id)
        pending = invoice.total - paid
        if pending > 0:
            open_invoices.append(OpenInvoiceItem(
                invoice_id=invoice.id,
                formatted_number=_formatted_number(invoice.point_of_sale, invoice.invoice_number),
                issue_date=invoice.issue_date,
                total=invoice.total,
                paid_amount=paid,
                pending_amount=pending,
            ))

    return AccountStatement(
        customer_id=customer.id,
        customer_name=customer.name,
        credit_limit=customer.credit_limit,
        balance=balance,
        available=available,
        movements=movements,
        open_invoices=open_invoices,
    )