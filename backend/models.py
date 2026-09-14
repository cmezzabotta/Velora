from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Numeric,
    Boolean,
    UniqueConstraint,
    Enum as SQLEnum,
)
from sqlalchemy.sql import func
import enum

from .database import Base




class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    currency = Column(String(10), nullable=False, default="USD")
    subscription_status = Column(
        String(20),
        nullable=False,
        default="active"
    )
    subscription_start = Column(DateTime, nullable=True)
    subscription_end = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer,
        ForeignKey("companies.id"),
        nullable=False,
        index=True
    )

    name = Column(
        String(150),
        nullable=False
    )

    sku = Column(
        String(100),
        nullable=True
    )

    description = Column(
        String(500),
        nullable=True
    )

    price = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    stock = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    active = Column(
        Boolean,
        nullable=False,
        default=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    tax_rate = Column(
        Numeric(5, 2),
        nullable=False,
        default=21.00
    )

class MovementType(str, enum.Enum):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"
    AJUSTE = "AJUSTE"
    TRANSFERENCIA = "TRANSFERENCIA"
    RESERVA = "RESERVA"
    LIBERACION = "LIBERACION"


class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )

    name = Column(String(100), nullable=False)
    address = Column(String(255), nullable=True)
    active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    warehouse_id = Column(
        Integer, ForeignKey("warehouses.id"), nullable=False, index=True
    )
    product_id = Column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )

    quantity = Column(Numeric(12, 2), nullable=False, default=0)
    reserved_quantity = Column(Numeric(12, 2), nullable=False, default=0)
    min_stock = Column(Numeric(12, 2), nullable=True)

    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "product_id", "warehouse_id", name="uq_product_warehouse"
        ),
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    warehouse_id = Column(
        Integer, ForeignKey("warehouses.id"), nullable=False, index=True
    )
    product_id = Column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )

    movement_type = Column(SQLEnum(MovementType), nullable=False)

    quantity = Column(Numeric(12, 2), nullable=False)
    previous_qty = Column(Numeric(12, 2), nullable=False)
    new_qty = Column(Numeric(12, 2), nullable=False)

    reference = Column(String(100), nullable=True)
    notes = Column(String(500), nullable=True)

    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer,
        ForeignKey("companies.id"),
        nullable=False,
        index=True
    )

    name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=False, unique=True)

    password_hash = Column(
        String(255),
        nullable=False
    )

    role = Column(
        String(30),
        nullable=False,
        default="admin"
    )

    active = Column(
        Boolean,
        nullable=False,
        default=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )


# ============================================================
# PEDIDOS — enums definidos ANTES de Order, porque Order los usa
# ============================================================

class OrderStatus(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    CONFIRMADO = "CONFIRMADO"
    PROGRAMADO = "PROGRAMADO"
    EN_CAMINO = "EN_CAMINO"
    ENTREGADO = "ENTREGADO"
    CANCELADO = "CANCELADO"


class DeliveryType(str, enum.Enum):
    ENVIO = "ENVIO"
    RETIRO = "RETIRO"


class PaymentMethod(str, enum.Enum):
    EFECTIVO = "EFECTIVO"
    TRANSFERENCIA = "TRANSFERENCIA"
    PENDIENTE = "PENDIENTE"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    customer_id = Column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    warehouse_id = Column(
        Integer, ForeignKey("warehouses.id"), nullable=False, index=True
    )

    delivery_address = Column(String(255), nullable=True)

    status = Column(
        SQLEnum(OrderStatus), nullable=False, default=OrderStatus.PENDIENTE
    )
    delivery_type = Column(SQLEnum(DeliveryType), nullable=True)
    scheduled_date = Column(DateTime, nullable=True)

    courier_name = Column(String(150), nullable=True)     
    received_by = Column(String(150), nullable=True)     
    delivered_at = Column(DateTime, nullable=True)   

    payment_method = Column(
        SQLEnum(PaymentMethod), nullable=False, default=PaymentMethod.PENDIENTE
    )
    paid = Column(Boolean, nullable=False, default=False)

    cancel_reason = Column(String(255), nullable=True)

    total = Column(Numeric(12, 2), nullable=False, default=0)

    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer, ForeignKey("orders.id"), nullable=False, index=True
    )
    product_id = Column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )

    quantity = Column(Numeric(12, 2), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)


class Sale(Base):
    __tablename__ = "sales"
 
    id = Column(Integer, primary_key=True, index=True)
 
    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    customer_id = Column(
        Integer, ForeignKey("customers.id"), nullable=True, index=True
    )  # null = consumidor final
    warehouse_id = Column(
        Integer, ForeignKey("warehouses.id"), nullable=False, index=True
    )
    cash_session_id = Column(
        Integer, ForeignKey("cash_sessions.id"), nullable=True, index=True
    )
    order_id = Column(
        Integer, ForeignKey("orders.id"), nullable=True, index=True
    )
 
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
 
    payment_method = Column(String(30), nullable=False, default="EFECTIVO")
    status = Column(String(30), nullable=False, default="completed")
 
    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )

class SaleItem(Base):
    __tablename__ = "sale_items"
 
    id = Column(Integer, primary_key=True, index=True)
 
    sale_id = Column(
        Integer, ForeignKey("sales.id"), nullable=False, index=True
    )
    product_id = Column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )
 
    quantity = Column(Numeric(12, 2), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    tax_rate = Column(Numeric(5, 2), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)

class CashSessionStatus(str, enum.Enum):
    ABIERTA = "ABIERTA"
    CERRADA = "CERRADA"
 
 
class CashMovementType(str, enum.Enum):
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"
 
 
class CashSession(Base):
    __tablename__ = "cash_sessions"
 
    id = Column(Integer, primary_key=True, index=True)
 
    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
 
    opening_amount = Column(Numeric(12, 2), nullable=False, default=0)
    opening_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )
 
    closing_amount = Column(Numeric(12, 2), nullable=True)
    expected_amount = Column(Numeric(12, 2), nullable=True)
    difference = Column(Numeric(12, 2), nullable=True)
    closing_at = Column(DateTime, nullable=True)
 
    status = Column(
        SQLEnum(CashSessionStatus), nullable=False, default=CashSessionStatus.ABIERTA
    )
    notes = Column(String(255), nullable=True)
 
 
class CashMovement(Base):
    __tablename__ = "cash_movements"
 
    id = Column(Integer, primary_key=True, index=True)
 
    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    cash_session_id = Column(
        Integer, ForeignKey("cash_sessions.id"), nullable=False, index=True
    )
 
    movement_type = Column(SQLEnum(CashMovementType), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String(255), nullable=True)
 
    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )

class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    company_id = Column(
        Integer,
        ForeignKey("companies.id"),
        nullable=False,
        index=True
    )

    order_id = Column(
        Integer,
        ForeignKey("orders.id"),
        nullable=True,
        index=True
    )

    customer_name = Column(
        String(150),
        nullable=False
    )

    address = Column(
        String(255),
        nullable=True
    )

    status = Column(
        String(30),
        nullable=False,
        default="pending"
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )


class Customer(Base):
    __tablename__ = "customers"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    company_id = Column(
        Integer,
        ForeignKey("companies.id"),
        nullable=False,
        index=True
    )

    # ========================================================
    # DATOS BÁSICOS
    # ========================================================

    name = Column(
        String(150),
        nullable=False
    )

    email = Column(
        String(255),
        nullable=True
    )

    phone = Column(
        String(50),
        nullable=True
    )

    address = Column(
        String(255),
        nullable=True
    )

    city = Column(
        String(100),
        nullable=True
    )

    tax_id = Column(
        String(50),
        nullable=True
    )

    # ========================================================
    # INFORMACIÓN COMERCIAL
    # ========================================================

    customer_type = Column(
        String(30),
        nullable=False,
        default="retail"
    )

    payment_terms = Column(
        String(30),
        nullable=False,
        default="cash"
    )

    credit_limit = Column(
        Numeric(12, 2),
        nullable=False,
        default=0
    )

    price_list = Column(
        Integer,
        nullable=False,
        default=1
    )

    # ========================================================
    # INFORMACIÓN FISCAL
    # ========================================================

    tax_condition = Column(
        String(50),
        nullable=True
    )

    # ========================================================
    # NOTAS / ESTADO
    # ========================================================

    notes = Column(
        String(500),
        nullable=True
    )

    active = Column(
        Boolean,
        nullable=False,
        default=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    # ============================================================
# AGREGAR a models.py — clases nuevas para Facturación
# ============================================================
# ============================================================
# AGREGAR a models.py — clases nuevas para Compras + Proveedores
# ============================================================

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )

    name = Column(String(150), nullable=False)
    tax_id = Column(String(50), nullable=True)
    contact_name = Column(String(150), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    payment_terms = Column(String(30), nullable=False, default="cash")
    notes = Column(String(500), nullable=True)

    active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )


class PurchaseStatus(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    RECIBIDA = "RECIBIDA"
    CANCELADA = "CANCELADA"


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    supplier_id = Column(
        Integer, ForeignKey("suppliers.id"), nullable=False, index=True
    )
    warehouse_id = Column(
        Integer, ForeignKey("warehouses.id"), nullable=False, index=True
    )

    status = Column(
        SQLEnum(PurchaseStatus), nullable=False, default=PurchaseStatus.PENDIENTE
    )

    supplier_invoice_number = Column(String(50), nullable=True)
    notes = Column(String(500), nullable=True)

    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)

    received_at = Column(DateTime, nullable=True)

    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)

    purchase_id = Column(
        Integer, ForeignKey("purchases.id"), nullable=False, index=True
    )
    product_id = Column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )

    quantity = Column(Numeric(12, 2), nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)
    
class InvoiceType(str, enum.Enum):
    A = "A"
    B = "B"
    C = "C"
    NOTA_CREDITO = "NOTA_CREDITO"
    NOTA_DEBITO = "NOTA_DEBITO"


class InvoiceStatus(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    AUTORIZADA = "AUTORIZADA"
    RECHAZADA = "RECHAZADA"
    ANULADA = "ANULADA"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    customer_id = Column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    order_id = Column(
        Integer, ForeignKey("orders.id"), nullable=True, index=True
    )

    invoice_type = Column(SQLEnum(InvoiceType), nullable=False)
    point_of_sale = Column(Integer, nullable=False, default=1)
    invoice_number = Column(Integer, nullable=False)

    issue_date = Column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Datos de autorización fiscal (CAE). En modo prueba, hasta
    # tener credenciales reales de ARCA, cae queda con prefijo
    # "TEST-" para dejar clarísimo que no es válido fiscalmente.
    cae = Column(String(50), nullable=True)
    cae_due_date = Column(DateTime, nullable=True)

    status = Column(
        SQLEnum(InvoiceStatus), nullable=False, default=InvoiceStatus.PENDIENTE
    )

    # Para notas de crédito/débito: a qué factura corrigen
    related_invoice_id = Column(
        Integer, ForeignKey("invoices.id"), nullable=True, index=True
    )

    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)

    payment_method = Column(String(30), nullable=True)

    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "company_id", "point_of_sale", "invoice_type", "invoice_number",
            name="uq_invoice_numbering"
        ),
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)

    invoice_id = Column(
        Integer, ForeignKey("invoices.id"), nullable=False, index=True
    )
    product_id = Column(
        Integer, ForeignKey("products.id"), nullable=False, index=True
    )

    quantity = Column(Numeric(12, 2), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    tax_rate = Column(Numeric(5, 2), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)

# ============================================================
# AGREGAR a models.py — clases nuevas para Cuentas Corrientes
# ============================================================

class AccountMovementType(str, enum.Enum):
    DEBITO = "DEBITO"
    CREDITO = "CREDITO"


class PaymentMethodCC(str, enum.Enum):
    EFECTIVO = "EFECTIVO"
    TRANSFERENCIA = "TRANSFERENCIA"
    CHEQUE = "CHEQUE"
    TARJETA = "TARJETA"
    OTRO = "OTRO"


class AccountMovement(Base):
    __tablename__ = "account_movements"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    customer_id = Column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )

    movement_type = Column(SQLEnum(AccountMovementType), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

    invoice_id = Column(
        Integer, ForeignKey("invoices.id"), nullable=True, index=True
    )
    payment_id = Column(
        Integer, ForeignKey("payments.id"), nullable=True, index=True
    )

    description = Column(String(255), nullable=True)
    balance_after = Column(Numeric(12, 2), nullable=False)

    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    customer_id = Column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )

    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(SQLEnum(PaymentMethodCC), nullable=False)
    payment_date = Column(
        DateTime, server_default=func.now(), nullable=False
    )
    notes = Column(String(255), nullable=True)

    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )


class PaymentApplication(Base):
    __tablename__ = "payment_applications"

    id = Column(Integer, primary_key=True, index=True)

    payment_id = Column(
        Integer, ForeignKey("payments.id"), nullable=False, index=True
    )
    invoice_id = Column(
        Integer, ForeignKey("invoices.id"), nullable=False, index=True
    )

    amount_applied = Column(Numeric(12, 2), nullable=False)