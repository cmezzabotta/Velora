from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy.orm import Session

from ..database import engine
from ..models import Customer, User
from ..schemas import (
    CustomerCreate,
    CustomerResponse,
)
from ..dependencies import get_current_user


router = APIRouter(
    prefix="/customers",
    tags=["Clientes"]
)


def get_db():
    with Session(engine) as session:
        yield session


# ============================================================
# OBTENER CLIENTES
# ============================================================

@router.get(
    "",
    response_model=list[CustomerResponse]
)
def get_customers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    customers = (
        db.query(Customer)
        .filter(
            Customer.company_id == current_user.company_id,
            Customer.active == True
        )
        .order_by(Customer.name.asc())
        .all()
    )

    return customers


# ============================================================
# CREAR CLIENTE
# ============================================================

@router.post(
    "",
    response_model=CustomerResponse
)
def create_customer(
    customer: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    new_customer = Customer(
        company_id=current_user.company_id,

        name=customer.name,
        email=customer.email,
        phone=customer.phone,

        address=customer.address,
        city=customer.city,

        tax_id=customer.tax_id,

        customer_type=customer.customer_type,
        payment_terms=customer.payment_terms,
        credit_limit=customer.credit_limit,
        price_list=customer.price_list,
        tax_condition=customer.tax_condition,

        notes=customer.notes,

        active=customer.active,
    )

    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)

    return new_customer


# ============================================================
# ACTUALIZAR CLIENTE
# ============================================================

@router.put(
    "/{customer_id}",
    response_model=CustomerResponse
)
def update_customer(
    customer_id: int,
    customer_data: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.company_id == current_user.company_id,
            Customer.active == True
        )
        .first()
    )

    if not customer:

        raise HTTPException(
            status_code=404,
            detail="Cliente no encontrado"
        )

    customer.name = customer_data.name
    customer.email = customer_data.email
    customer.phone = customer_data.phone

    customer.address = customer_data.address
    customer.city = customer_data.city

    customer.tax_id = customer_data.tax_id

    customer.customer_type = customer_data.customer_type
    customer.payment_terms = customer_data.payment_terms
    customer.credit_limit = customer_data.credit_limit
    customer.price_list = customer_data.price_list
    customer.tax_condition = customer_data.tax_condition

    customer.notes = customer_data.notes

    customer.active = customer_data.active

    db.commit()
    db.refresh(customer)

    return customer


# ============================================================
# ELIMINAR CLIENTE
# ============================================================

@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.company_id == current_user.company_id,
            Customer.active == True
        )
        .first()
    )

    if not customer:

        raise HTTPException(
            status_code=404,
            detail="Cliente no encontrado"
        )

    customer.active = False

    db.commit()

    return {
        "message": "Cliente eliminado correctamente"
    }