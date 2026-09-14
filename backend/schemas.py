from pydantic import BaseModel
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal
import enum



class CompanyCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    currency: str = "USD"


class CompanyResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    currency: str
    subscription_status: str

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str
    sku: str | None = None
    description: str | None = None
    price: float
    stock: float = 0
    tax_rate: float = 21.00
    active: bool = True
 
 
class ProductResponse(BaseModel):
    id: int
    company_id: int
    name: str
    sku: str | None
    description: str | None
    price: float
    stock: float
    tax_rate: float
    active: bool
 
    class Config:
        from_attributes = True

class CustomerCreate(BaseModel):
    name: str

    email: Optional[str] = None
    phone: Optional[str] = None

    address: Optional[str] = None
    city: Optional[str] = None

    tax_id: Optional[str] = None

    customer_type: str = "retail"

    payment_terms: str = "cash"

    credit_limit: float = 0

    price_list: int = 1

    tax_condition: Optional[str] = None

    notes: Optional[str] = None

    active: bool = True


class CustomerResponse(BaseModel):
    id: int

    company_id: int

    name: str

    email: Optional[str] = None
    phone: Optional[str] = None

    address: Optional[str] = None
    city: Optional[str] = None

    tax_id: Optional[str] = None

    customer_type: str

    payment_terms: str

    credit_limit: float

    price_list: int

    tax_condition: Optional[str] = None

    notes: Optional[str] = None

    active: bool

    class Config:
        from_attributes = True

class MovementType(str, enum.Enum):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"
    AJUSTE = "AJUSTE"
    TRANSFERENCIA = "TRANSFERENCIA"
    RESERVA = "RESERVA"
    LIBERACION = "LIBERACION"


# ============================================================
# WAREHOUSE
# ============================================================

class WarehouseCreate(BaseModel):
    name: str
    address: Optional[str] = None


class WarehouseUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    active: Optional[bool] = None


class WarehouseResponse(BaseModel):
    id: int
    company_id: int
    name: str
    address: Optional[str]
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# INVENTORY
# ============================================================

class InventoryCreate(BaseModel):
    """
    Crea la fila inicial de stock de un producto en un depósito.
    No se usa para sumar/restar cantidades después de creada;
    para eso se usa el endpoint de ajuste, que genera StockMovement.
    """
    warehouse_id: int
    product_id: int
    quantity: Decimal = Field(default=0, ge=0)
    min_stock: Optional[Decimal] = None


class InventoryUpdate(BaseModel):
    """Solo permite tocar min_stock directamente. La cantidad se
    modifica exclusivamente vía /stock/movements para dejar rastro."""
    min_stock: Optional[Decimal] = None


class InventoryResponse(BaseModel):
    id: int
    company_id: int
    warehouse_id: int
    product_id: int
    quantity: Decimal
    reserved_quantity: Decimal
    available: Decimal
    min_stock: Optional[Decimal]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# STOCK MOVEMENT
# ============================================================

class StockMovementCreate(BaseModel):
    """
    Input para registrar un movimiento. El backend calcula
    previous_qty / new_qty automáticamente a partir del
    inventory actual — el cliente nunca los envía.
    """
    warehouse_id: int
    product_id: int
    movement_type: MovementType
    quantity: Decimal = Field(gt=0)
    reference: Optional[str] = None
    notes: Optional[str] = None


class StockMovementResponse(BaseModel):
    id: int
    company_id: int
    warehouse_id: int
    product_id: int
    user_id: Optional[int]
    movement_type: MovementType
    quantity: Decimal
    previous_qty: Decimal
    new_qty: Decimal
    reference: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# PEDIDOS
# ============================================================

class OrderStatus(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    CONFIRMADO = "CONFIRMADO"
    PROGRAMADO = "PROGRAMADO"
    EN_CAMINO = "EN_CAMINO"
    ENTREGADO = "ENTREGADO"
    CANCELADO = "CANCELADO"

class OrderDispatch(BaseModel):
    courier_name: str

class OrderDeliver(BaseModel):
    received_by: Optional[str] = None

class DeliveryType(str, enum.Enum):
    ENVIO = "ENVIO"
    RETIRO = "RETIRO"


class PaymentMethod(str, enum.Enum):
    EFECTIVO = "EFECTIVO"
    TRANSFERENCIA = "TRANSFERENCIA"
    PENDIENTE = "PENDIENTE"


# ============================================================
# ORDER ITEM
# ============================================================

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)
    # unit_price es opcional: si no se manda, se toma el precio
    # actual del producto en el momento de crear el pedido.
    unit_price: Optional[Decimal] = None


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal

    class Config:
        from_attributes = True


# ============================================================
# ORDER
# ============================================================

class OrderCreate(BaseModel):
    customer_id: int
    warehouse_id: int
    delivery_address: Optional[str] = None
    items: List[OrderItemCreate]


class OrderConfirm(BaseModel):
    payment_method: PaymentMethod


class OrderSchedule(BaseModel):
    delivery_type: DeliveryType
    scheduled_date: Optional[datetime] = None  # requerido si es ENVIO


class OrderCancel(BaseModel):
    cancel_reason: str


class OrderResponse(BaseModel):
    id: int
    company_id: int
    customer_id: int
    warehouse_id: int
    delivery_address: Optional[str]
    status: OrderStatus
    delivery_type: Optional[DeliveryType]
    scheduled_date: Optional[datetime]
    payment_method: PaymentMethod
    paid: bool
    cancel_reason: Optional[str]
    courier_name: Optional[str]
    received_by: Optional[str]
    delivered_at: Optional[datetime]
    total: Decimal
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = []
 
    class Config:
        from_attributes = True


class OrderListItem(BaseModel):
    id: int
    customer_name: str
    delivery_address: Optional[str]
    status: OrderStatus
    delivery_type: Optional[DeliveryType]
    scheduled_date: Optional[datetime]
    courier_name: Optional[str]
    items_summary: str
    total_products: int
    total_quantity: Decimal
    total: Decimal
    created_at: datetime
 
    class Config:
        from_attributes = True

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
 
 
class InvoiceItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Optional[Decimal] = None   # si no se manda, toma el del producto
    tax_rate: Optional[Decimal] = None     # si no se manda, toma el del producto
 
 
class InvoiceItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    subtotal: Decimal
 
    class Config:
        from_attributes = True
 
 
class InvoiceCreate(BaseModel):
    """
    Si se manda order_id, la factura toma cliente e items
    directamente del pedido (se ignora customer_id/items).
    Si no, es una factura manual: requiere customer_id + items.
    """
    order_id: Optional[int] = None
    customer_id: Optional[int] = None
    invoice_type: InvoiceType
    point_of_sale: int = 1
    payment_method: Optional[str] = None
    items: Optional[List[InvoiceItemCreate]] = None
 
 
class InvoiceResponse(BaseModel):
    id: int
    company_id: int
    customer_id: int
    order_id: Optional[int]
    invoice_type: InvoiceType
    point_of_sale: int
    invoice_number: int
    issue_date: datetime
    cae: Optional[str]
    cae_due_date: Optional[datetime]
    status: InvoiceStatus
    related_invoice_id: Optional[int]
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    payment_method: Optional[str]
    created_at: datetime
    items: List[InvoiceItemResponse] = []
    credit_warning: Optional[str] = None
 
    class Config:
        from_attributes = True
 
 
class InvoiceListItem(BaseModel):
    id: int
    customer_name: str
    invoice_type: InvoiceType
    formatted_number: str  # "0001-00001234"
    issue_date: datetime
    status: InvoiceStatus
    total: Decimal
 
    class Config:
        from_attributes = True

# ============================================================
# NUEVO: agregar a schemas.py
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


class PaymentApplicationCreate(BaseModel):
    invoice_id: int
    amount_applied: Decimal = Field(gt=0)


class PaymentCreate(BaseModel):
    customer_id: int
    amount: Decimal = Field(gt=0)
    payment_method: PaymentMethodCC
    payment_date: Optional[datetime] = None
    notes: Optional[str] = None
    applications: Optional[List[PaymentApplicationCreate]] = None


class PaymentApplicationResponse(BaseModel):
    id: int
    invoice_id: int
    amount_applied: Decimal

    class Config:
        from_attributes = True


class PaymentResponse(BaseModel):
    id: int
    company_id: int
    customer_id: int
    amount: Decimal
    payment_method: PaymentMethodCC
    payment_date: datetime
    notes: Optional[str]
    created_at: datetime
    applications: List[PaymentApplicationResponse] = []

    class Config:
        from_attributes = True


class AccountMovementResponse(BaseModel):
    id: int
    customer_id: int
    movement_type: AccountMovementType
    amount: Decimal
    invoice_id: Optional[int]
    payment_id: Optional[int]
    description: Optional[str]
    balance_after: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class OpenInvoiceItem(BaseModel):
    """Factura con saldo pendiente, para elegir a qué aplicar un pago."""
    invoice_id: int
    formatted_number: str
    issue_date: datetime
    total: Decimal
    paid_amount: Decimal
    pending_amount: Decimal


class AccountStatement(BaseModel):
    customer_id: int
    customer_name: str
    credit_limit: Decimal
    balance: Decimal
    available: Decimal
    movements: List[AccountMovementResponse]
    open_invoices: List[OpenInvoiceItem]

# ============================================================
# AGREGAR a schemas.py — Proveedores + Compras
# ============================================================

class SupplierCreate(BaseModel):
    name: str
    tax_id: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    payment_terms: str = "cash"
    notes: Optional[str] = None
    active: bool = True


class SupplierResponse(BaseModel):
    id: int
    company_id: int
    name: str
    tax_id: Optional[str]
    contact_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    city: Optional[str]
    payment_terms: str
    notes: Optional[str]
    active: bool

    class Config:
        from_attributes = True


class PurchaseStatus(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    RECIBIDA = "RECIBIDA"
    CANCELADA = "CANCELADA"


class PurchaseItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


class PurchaseItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: Decimal
    unit_cost: Decimal
    subtotal: Decimal

    class Config:
        from_attributes = True


class PurchaseCreate(BaseModel):
    supplier_id: int
    warehouse_id: int
    supplier_invoice_number: Optional[str] = None
    notes: Optional[str] = None
    items: List[PurchaseItemCreate]


class PurchaseResponse(BaseModel):
    id: int
    company_id: int
    supplier_id: int
    warehouse_id: int
    status: PurchaseStatus
    supplier_invoice_number: Optional[str]
    notes: Optional[str]
    subtotal: Decimal
    total: Decimal
    received_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: List[PurchaseItemResponse] = []

    class Config:
        from_attributes = True


class PurchaseListItem(BaseModel):
    id: int
    supplier_name: str
    status: PurchaseStatus
    items_summary: str
    total: Decimal
    created_at: datetime

    class Config:
        from_attributes = True

# ============================================================
# AGREGAR a schemas.py — POS y Caja
# ============================================================

class CashSessionStatus(str, enum.Enum):
    ABIERTA = "ABIERTA"
    CERRADA = "CERRADA"


class CashMovementType(str, enum.Enum):
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"


# ------------------------------------------------------------
# CAJA
# ------------------------------------------------------------

class CashSessionOpen(BaseModel):
    opening_amount: Decimal = Field(ge=0)
    notes: Optional[str] = None


class CashSessionClose(BaseModel):
    closing_amount: Decimal = Field(ge=0)
    notes: Optional[str] = None


class CashMovementCreate(BaseModel):
    movement_type: CashMovementType
    amount: Decimal = Field(gt=0)
    description: Optional[str] = None


class CashMovementResponse(BaseModel):
    id: int
    cash_session_id: int
    movement_type: CashMovementType
    amount: Decimal
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CashSessionResponse(BaseModel):
    id: int
    company_id: int
    user_id: int
    opening_amount: Decimal
    opening_at: datetime
    closing_amount: Optional[Decimal]
    expected_amount: Optional[Decimal]
    difference: Optional[Decimal]
    closing_at: Optional[datetime]
    status: CashSessionStatus
    notes: Optional[str]
    movements: List[CashMovementResponse] = []

    class Config:
        from_attributes = True


# ------------------------------------------------------------
# POS / VENTAS
# ------------------------------------------------------------

class SaleItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)
    unit_price: Optional[Decimal] = None  # si no se manda, toma el del producto


class SaleItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    subtotal: Decimal

    class Config:
        from_attributes = True


class SaleCreate(BaseModel):
    warehouse_id: int
    customer_id: Optional[int] = None  # null = consumidor final
    payment_method: str = "EFECTIVO"
    items: List[SaleItemCreate]


class SaleResponse(BaseModel):
    id: int
    company_id: int
    customer_id: Optional[int]
    warehouse_id: int
    cash_session_id: Optional[int]
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    payment_method: str
    status: str
    created_at: datetime
    items: List[SaleItemResponse] = []

    class Config:
        from_attributes = True


class SaleListItem(BaseModel):
    id: int
    customer_name: str
    items_summary: str
    total: Decimal
    payment_method: str
    created_at: datetime

    class Config:
        from_attributes = True