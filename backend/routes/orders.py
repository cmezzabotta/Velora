from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

from ..dependencies import get_db, get_current_user
from ..models import (
    Order,
    OrderItem,
    Customer,
    Product,
    Inventory,
    StockMovement,
    MovementType,
    OrderStatus as ModelOrderStatus,
    DeliveryType as ModelDeliveryType,
)
from ..schemas import (
    OrderCreate,
    OrderConfirm,
    OrderSchedule,
    OrderCancel,
    OrderDispatch,
    OrderDeliver,
    OrderResponse,
    OrderListItem,
    OrderStatus,
    DeliveryType,
)

router = APIRouter(prefix="/orders", tags=["Pedidos"])


# ============================================================
# HELPERS
# ============================================================

def _get_order_or_404(order_id: int, db: Session, company_id: int) -> Order:
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.company_id == company_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return order


def _items_summary(items: List[OrderItem], products_map: dict) -> str:
    names = [products_map.get(item.product_id, f"#{item.product_id}") for item in items]
    if len(names) <= 2:
        return ", ".join(names)
    return f"{names[0]}, {names[1]} y {len(names) - 2} más"


def _reserve_stock_for_order(order: Order, db: Session, user_id: Optional[int]):
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()

    inventories = {}
    for item in items:
        inv = (
            db.query(Inventory)
            .filter(
                Inventory.company_id == order.company_id,
                Inventory.warehouse_id == order.warehouse_id,
                Inventory.product_id == item.product_id,
            )
            .first()
        )
        available = (inv.quantity - inv.reserved_quantity) if inv else Decimal(0)
        if item.quantity > available:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente para el producto #{item.product_id}. "
                       f"Disponible: {available}, solicitado: {item.quantity}",
            )
        inventories[item.id] = inv

    for item in items:
        inv = inventories[item.id]
        previous_qty = inv.quantity
        inv.reserved_quantity = inv.reserved_quantity + item.quantity

        db.add(StockMovement(
            company_id=order.company_id,
            warehouse_id=order.warehouse_id,
            product_id=item.product_id,
            user_id=user_id,
            movement_type=MovementType.RESERVA,
            quantity=item.quantity,
            previous_qty=previous_qty,
            new_qty=inv.quantity,
            reference=f"Pedido #{order.id}",
        ))


def _release_stock_for_order(order: Order, db: Session, user_id: Optional[int]):
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()

    for item in items:
        inv = (
            db.query(Inventory)
            .filter(
                Inventory.company_id == order.company_id,
                Inventory.warehouse_id == order.warehouse_id,
                Inventory.product_id == item.product_id,
            )
            .first()
        )
        if not inv:
            continue

        release_qty = min(item.quantity, inv.reserved_quantity)
        if release_qty <= 0:
            continue

        previous_qty = inv.quantity
        inv.reserved_quantity = inv.reserved_quantity - release_qty

        db.add(StockMovement(
            company_id=order.company_id,
            warehouse_id=order.warehouse_id,
            product_id=item.product_id,
            user_id=user_id,
            movement_type=MovementType.LIBERACION,
            quantity=release_qty,
            previous_qty=previous_qty,
            new_qty=inv.quantity,
            reference=f"Pedido #{order.id} cancelado",
        ))


def _deliver_stock_for_order(order: Order, db: Session, user_id: Optional[int]):
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()

    for item in items:
        inv = (
            db.query(Inventory)
            .filter(
                Inventory.company_id == order.company_id,
                Inventory.warehouse_id == order.warehouse_id,
                Inventory.product_id == item.product_id,
            )
            .first()
        )
        if not inv:
            raise HTTPException(
                status_code=400,
                detail=f"No hay inventario del producto #{item.product_id} para entregar",
            )

        release_qty = min(item.quantity, inv.reserved_quantity)
        if release_qty > 0:
            prev = inv.quantity
            inv.reserved_quantity = inv.reserved_quantity - release_qty
            db.add(StockMovement(
                company_id=order.company_id,
                warehouse_id=order.warehouse_id,
                product_id=item.product_id,
                user_id=user_id,
                movement_type=MovementType.LIBERACION,
                quantity=release_qty,
                previous_qty=prev,
                new_qty=inv.quantity,
                reference=f"Pedido #{order.id} entregado",
            ))

        if item.quantity > inv.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Stock físico insuficiente para entregar el producto #{item.product_id}",
            )
        prev = inv.quantity
        inv.quantity = inv.quantity - item.quantity
        db.add(StockMovement(
            company_id=order.company_id,
            warehouse_id=order.warehouse_id,
            product_id=item.product_id,
            user_id=user_id,
            movement_type=MovementType.SALIDA,
            quantity=item.quantity,
            previous_qty=prev,
            new_qty=inv.quantity,
            reference=f"Pedido #{order.id} entregado",
        ))


# ============================================================
# LISTAR
# ============================================================

@router.get("", response_model=List[OrderListItem])
def list_orders(
    status: Optional[OrderStatus] = None,
    delivery_type: Optional[DeliveryType] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Order).filter(Order.company_id == current_user.company_id)
    if status:
        query = query.filter(Order.status == status)
    if delivery_type:
        query = query.filter(Order.delivery_type == delivery_type)

    orders = query.order_by(Order.created_at.desc()).all()

    if not orders:
        return []

    customer_ids = {o.customer_id for o in orders}
    customers_map = {
        c.id: c.name
        for c in db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
    }

    order_ids = [o.id for o in orders]
    all_items = (
        db.query(OrderItem).filter(OrderItem.order_id.in_(order_ids)).all()
    )
    items_by_order = {}
    for item in all_items:
        items_by_order.setdefault(item.order_id, []).append(item)

    product_ids = {item.product_id for item in all_items}
    products_map = {
        p.id: p.name
        for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
    }

    result = []
    for order in orders:
        items = items_by_order.get(order.id, [])
        result.append(OrderListItem(
            id=order.id,
            customer_name=customers_map.get(order.customer_id, "Cliente desconocido"),
            delivery_address=order.delivery_address,
            status=order.status,
            delivery_type=order.delivery_type,
            scheduled_date=order.scheduled_date,
            courier_name=order.courier_name,
            items_summary=_items_summary(items, products_map),
            total_products=len(items),
            total_quantity=sum((item.quantity for item in items), Decimal(0)),
            total=order.total,
            created_at=order.created_at,
        ))

    return result


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = _get_order_or_404(order_id, db, current_user.company_id)
    return order


# ============================================================
# CREAR PEDIDO
# ============================================================

@router.post("", response_model=OrderResponse)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    customer = (
        db.query(Customer)
        .filter(
            Customer.id == payload.customer_id,
            Customer.company_id == current_user.company_id,
        )
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if not payload.items:
        raise HTTPException(status_code=400, detail="El pedido necesita al menos un producto")

    order = Order(
        company_id=current_user.company_id,
        customer_id=payload.customer_id,
        warehouse_id=payload.warehouse_id,
        delivery_address=payload.delivery_address or customer.address,
        status=ModelOrderStatus.PENDIENTE,
        total=0,
    )
    db.add(order)
    db.flush()

    total = Decimal(0)
    for item_payload in payload.items:
        product = (
            db.query(Product)
            .filter(
                Product.id == item_payload.product_id,
                Product.company_id == current_user.company_id,
            )
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Producto #{item_payload.product_id} no encontrado",
            )

        unit_price = item_payload.unit_price if item_payload.unit_price is not None else product.price
        subtotal = unit_price * item_payload.quantity
        total += subtotal

        db.add(OrderItem(
            order_id=order.id,
            product_id=item_payload.product_id,
            quantity=item_payload.quantity,
            unit_price=unit_price,
            subtotal=subtotal,
        ))

    order.total = total

    db.commit()
    db.refresh(order)
    return order


# ============================================================
# CONFIRMAR (pago + reserva de stock)
# ============================================================

@router.post("/{order_id}/confirm", response_model=OrderResponse)
def confirm_order(
    order_id: int,
    payload: OrderConfirm,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = _get_order_or_404(order_id, db, current_user.company_id)

    if order.status != ModelOrderStatus.PENDIENTE:
        raise HTTPException(
            status_code=400,
            detail=f"Solo se puede confirmar un pedido PENDIENTE (estado actual: {order.status.value})",
        )

    _reserve_stock_for_order(order, db, current_user.id)

    order.payment_method = payload.payment_method
    order.paid = payload.payment_method != "PENDIENTE"
    order.status = ModelOrderStatus.CONFIRMADO

    db.commit()
    db.refresh(order)
    return order


# ============================================================
# PROGRAMAR ENVÍO / RETIRO
# ============================================================

@router.post("/{order_id}/schedule", response_model=OrderResponse)
def schedule_order(
    order_id: int,
    payload: OrderSchedule,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = _get_order_or_404(order_id, db, current_user.company_id)

    if order.status != ModelOrderStatus.CONFIRMADO:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede programar un pedido ya CONFIRMADO",
        )

    if payload.delivery_type == DeliveryType.ENVIO and not payload.scheduled_date:
        raise HTTPException(
            status_code=400,
            detail="Un envío necesita fecha y hora programada",
        )

    order.delivery_type = payload.delivery_type
    order.scheduled_date = payload.scheduled_date
    order.status = ModelOrderStatus.PROGRAMADO

    db.commit()
    db.refresh(order)
    return order


# ============================================================
# DESPACHAR (asignar repartidor, solo ENVIO: PROGRAMADO -> EN_CAMINO)
# ============================================================

@router.post("/{order_id}/dispatch", response_model=OrderResponse)
def dispatch_order(
    order_id: int,
    payload: OrderDispatch,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = _get_order_or_404(order_id, db, current_user.company_id)

    if order.delivery_type != ModelDeliveryType.ENVIO:
        raise HTTPException(
            status_code=400,
            detail="Solo los pedidos con envío pasan por 'en camino'. "
                   "Un retiro se marca directamente como entregado.",
        )

    if order.status != ModelOrderStatus.PROGRAMADO:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede despachar un pedido PROGRAMADO",
        )

    order.courier_name = payload.courier_name
    order.status = ModelOrderStatus.EN_CAMINO

    db.commit()
    db.refresh(order)
    return order


# ============================================================
# ENTREGAR
# ============================================================

@router.post("/{order_id}/deliver", response_model=OrderResponse)
def deliver_order(
    order_id: int,
    payload: OrderDeliver,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = _get_order_or_404(order_id, db, current_user.company_id)

    # RETIRO se entrega directo desde PROGRAMADO.
    # ENVIO necesita haber pasado por EN_CAMINO primero.
    if order.delivery_type == ModelDeliveryType.ENVIO:
        valid_previous = ModelOrderStatus.EN_CAMINO
    else:
        valid_previous = ModelOrderStatus.PROGRAMADO

    if order.status != valid_previous:
        raise HTTPException(
            status_code=400,
            detail=f"Este pedido debe estar en estado {valid_previous.value} para entregarse "
                   f"(estado actual: {order.status.value})",
        )

    _deliver_stock_for_order(order, db, current_user.id)
    order.status = ModelOrderStatus.ENTREGADO
    order.received_by = payload.received_by
    order.delivered_at = datetime.utcnow()

    db.commit()
    db.refresh(order)
    return order


# ============================================================
# CANCELAR
# ============================================================

@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    payload: OrderCancel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    order = _get_order_or_404(order_id, db, current_user.company_id)

    if order.status in (ModelOrderStatus.ENTREGADO, ModelOrderStatus.CANCELADO):
        raise HTTPException(
            status_code=400,
            detail=f"No se puede cancelar un pedido {order.status.value}",
        )

    if order.status in (ModelOrderStatus.CONFIRMADO, ModelOrderStatus.PROGRAMADO, ModelOrderStatus.EN_CAMINO):
        _release_stock_for_order(order, db, current_user.id)

    order.status = ModelOrderStatus.CANCELADO
    order.cancel_reason = payload.cancel_reason

    db.commit()
    db.refresh(order)
    return order