from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .routes.dashboard import router as dashboard_router
from .routes.products import router as products_router
from .routes.customers import router as customers_router
from .routes.stock import router as stock_router
from .routes.orders import router as orders_router
from .routes.invoices import router as invoices_router
from .routes.payments import payments_router, accounts_router
from .routes.suppliers import router as suppliers_router
from .routes.purchases import router as purchases_router
from .routes.cash import router as cash_router
from .routes.pos import router as pos_router
from .routes.reports import router as reports_router
from .routes.company import router as company_router

from .database import engine
from .models import Company, Product, User
from .schemas import (
    CompanyCreate,
    CompanyResponse,
    ProductCreate,
    ProductResponse
)
from .auth import router as auth_router
from .dependencies import get_current_user


app = FastAPI(
    title="Velora API",
    version="1.0.0"
)

app.include_router(dashboard_router)
app.include_router(products_router)
app.include_router(customers_router)
app.include_router(stock_router)
app.include_router(orders_router)
app.include_router(invoices_router)
app.include_router(payments_router)
app.include_router(accounts_router)
app.include_router(suppliers_router)
app.include_router(purchases_router)
app.include_router(cash_router)
app.include_router(pos_router)
app.include_router(reports_router)
app.include_router(company_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)


@app.get("/")
def inicio():
    return {
        "mensaje": "Velora API funcionando",
        "version": "1.0.0"
    }


@app.post("/companies", response_model=CompanyResponse)
def create_company(company: CompanyCreate):

    with Session(engine) as session:

        nueva_empresa = Company(
            name=company.name,
            email=company.email,
            phone=company.phone,
            country=company.country,
            currency=company.currency
        )

        session.add(nueva_empresa)
        session.commit()
        session.refresh(nueva_empresa)

        return nueva_empresa
    

@app.post("/products", response_model=ProductResponse)
def create_product(
    product: ProductCreate,
    current_user: User = Depends(get_current_user),
):

    with Session(engine) as session:

        nuevo_producto = Product(
            company_id=current_user.company_id,
            name=product.name,
            sku=product.sku,
            description=product.description,
            price=product.price,
            stock=product.stock,
            active=product.active
        )

        session.add(nuevo_producto)
        session.commit()
        session.refresh(nuevo_producto)

        return nuevo_producto