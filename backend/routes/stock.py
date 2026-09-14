from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from decimal import Decimal

from ..dependencies import get_db, get_current_user
from ..models import Warehouse, Inventory, StockMovement, MovementType as ModelMovementType
from ..schemas import (
    WarehouseCreate,
    WarehouseUpdate,
    WarehouseResponse,
    InventoryCreate,
    InventoryUpdate,
    InventoryResponse,
    StockMovementCreate,
    StockMovementResponse,
    MovementType,
)

router = APIRouter(prefix="/stock", tags=["Stock"])


def _to_inventory_response(inv: Inventory) -> InventoryResponse:
    return InventoryResponse(
        id=inv.id,
        company_id=inv.company_id,
        warehouse_id=inv.warehouse_id,
        product_id=inv.product_id,
        quantity=inv.quantity,
        reserved_quantity=inv.reserved_quantity,
        available=inv.quantity - inv.reserved_quantity,
        min_stock=inv.min_stock,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
    )


# ============================================================
# WAREHOUSES
# ============================================================

@router.get("/warehouses", response_model=List[WarehouseResponse])
def list_warehouses(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return (
        db.query(Warehouse)
        .filter(Warehouse.company_id == current_user.company_id)
        .order_by(Warehouse.name)
        .all()
    )


@router.post("/warehouses", response_model=WarehouseResponse)
def create_warehouse(
    payload: WarehouseCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    warehouse = Warehouse(
        company_id=current_user.company_id,
        name=payload.name,
        address=payload.address,
    )
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)
    return warehouse


@router.put("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    warehouse = (
        db.query(Warehouse)
        .filter(
            Warehouse.id == warehouse_id,
            Warehouse.company_id == current_user.company_id,
        )
        .first()
    )
    if not warehouse:
        raise HTTPException(status_code=404, detail="Depósito no encontrado")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(warehouse, field, value)

    db.commit()
    db.refresh(warehouse)
    return warehouse


@router.delete("/warehouses/{warehouse_id}")
def delete_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    warehouse = (
        db.query(Warehouse)
        .filter(
            Warehouse.id == warehouse_id,
            Warehouse.company_id == current_user.company_id,
        )
        .first()
    )
    if not warehouse:
        raise HTTPException(status_code=404, detail="Depósito no encontrado")

    # Soft delete, mismo patrón que Customer
    warehouse.active = False
    db.commit()
    return {"detail": "Depósito desactivado"}


# ============================================================
# INVENTORY (lectura + creación inicial + min_stock)
# ============================================================

@router.get("/inventory", response_model=List[InventoryResponse])
def list_inventory(
    warehouse_id: int = None,
    product_id: int = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Inventory).filter(
        Inventory.company_id == current_user.company_id
    )
    if warehouse_id:
        query = query.filter(Inventory.warehouse_id == warehouse_id)
    if product_id:
        query = query.filter(Inventory.product_id == product_id)

    return [_to_inventory_response(inv) for inv in query.all()]


@router.post("/inventory", response_model=InventoryResponse)
def create_inventory(
    payload: InventoryCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    existing = (
        db.query(Inventory)
        .filter(
            Inventory.company_id == current_user.company_id,
            Inventory.warehouse_id == payload.warehouse_id,
            Inventory.product_id == payload.product_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una fila de inventario para ese producto en ese depósito",
        )

    inv = Inventory(
        company_id=current_user.company_id,
        warehouse_id=payload.warehouse_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        reserved_quantity=0,
        min_stock=payload.min_stock,
    )
    db.add(inv)

    # Si arranca con cantidad > 0, dejamos registrado el movimiento inicial
    if payload.quantity and payload.quantity > 0:
        db.flush()  # para tener inv.id disponible si se necesitara
        movement = StockMovement(
            company_id=current_user.company_id,
            warehouse_id=payload.warehouse_id,
            product_id=payload.product_id,
            user_id=current_user.id,
            movement_type=ModelMovementType.ENTRADA,
            quantity=payload.quantity,
            previous_qty=0,
            new_qty=payload.quantity,
            reference="Carga inicial de inventario",
        )
        db.add(movement)

    db.commit()
    db.refresh(inv)
    return _to_inventory_response(inv)


@router.put("/inventory/{inventory_id}", response_model=InventoryResponse)
def update_inventory(
    inventory_id: int,
    payload: InventoryUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Solo permite editar min_stock. La cantidad NUNCA se toca acá:
    para eso está /stock/movements, que deja rastro en StockMovement."""
    inv = (
        db.query(Inventory)
        .filter(
            Inventory.id == inventory_id,
            Inventory.company_id == current_user.company_id,
        )
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Registro de inventario no encontrado")

    if payload.min_stock is not None:
        inv.min_stock = payload.min_stock

    db.commit()
    db.refresh(inv)
    return _to_inventory_response(inv)


# ============================================================
# STOCK MOVEMENTS — única puerta de entrada para cambiar cantidades
# ============================================================

@router.get("/movements", response_model=List[StockMovementResponse])
def list_movements(
    warehouse_id: int = None,
    product_id: int = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(StockMovement).filter(
        StockMovement.company_id == current_user.company_id
    )
    if warehouse_id:
        query = query.filter(StockMovement.warehouse_id == warehouse_id)
    if product_id:
        query = query.filter(StockMovement.product_id == product_id)

    return query.order_by(StockMovement.created_at.desc()).all()


@router.post("/movements", response_model=StockMovementResponse)
def create_movement(
    payload: StockMovementCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Punto único de verdad para modificar cantidades de stock.
    Aplica el efecto sobre Inventory y registra el StockMovement
    en la misma transacción, con snapshots previous_qty/new_qty.

    Semántica de 'quantity' según movement_type:
      ENTRADA        -> se SUMA a quantity
      SALIDA         -> se RESTA de quantity (valida que no quede negativo)
      AJUSTE         -> quantity es el valor ABSOLUTO final de quantity
      RESERVA        -> se SUMA a reserved_quantity (valida contra disponible)
      LIBERACION     -> se RESTA de reserved_quantity
      TRANSFERENCIA  -> no soportado todavía (requiere dos depósitos);
                        se implementa junto con Pedidos.
    """
    if payload.movement_type == MovementType.TRANSFERENCIA:
        raise HTTPException(
            status_code=400,
            detail="TRANSFERENCIA todavía no está implementada. "
                   "Usá SALIDA en el depósito origen y ENTRADA en el destino.",
        )

    inv = (
        db.query(Inventory)
        .filter(
            Inventory.company_id == current_user.company_id,
            Inventory.warehouse_id == payload.warehouse_id,
            Inventory.product_id == payload.product_id,
        )
        .first()
    )

    # Si no existe fila de inventory todavía y el movimiento es ENTRADA,
    # la creamos sobre la marcha en vez de forzar al usuario a un paso extra.
    if not inv:
        if payload.movement_type != MovementType.ENTRADA:
            raise HTTPException(
                status_code=404,
                detail="No existe stock de ese producto en ese depósito. "
                       "Registrá primero una ENTRADA.",
            )
        inv = Inventory(
            company_id=current_user.company_id,
            warehouse_id=payload.warehouse_id,
            product_id=payload.product_id,
            quantity=0,
            reserved_quantity=0,
        )
        db.add(inv)
        db.flush()

    previous_qty = inv.quantity

    if payload.movement_type == MovementType.ENTRADA:
        inv.quantity = inv.quantity + payload.quantity

    elif payload.movement_type == MovementType.SALIDA:
        if payload.quantity > inv.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente. Disponible físico: {inv.quantity}",
            )
        inv.quantity = inv.quantity - payload.quantity

    elif payload.movement_type == MovementType.AJUSTE:
        inv.quantity = payload.quantity

    elif payload.movement_type == MovementType.RESERVA:
        disponible = inv.quantity - inv.reserved_quantity
        if payload.quantity > disponible:
            raise HTTPException(
                status_code=400,
                detail=f"No hay suficiente stock disponible para reservar. Disponible: {disponible}",
            )
        inv.reserved_quantity = inv.reserved_quantity + payload.quantity

    elif payload.movement_type == MovementType.LIBERACION:
        if payload.quantity > inv.reserved_quantity:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede liberar más de lo reservado. Reservado: {inv.reserved_quantity}",
            )
        inv.reserved_quantity = inv.reserved_quantity - payload.quantity

    new_qty = inv.quantity

    movement = StockMovement(
        company_id=current_user.company_id,
        warehouse_id=payload.warehouse_id,
        product_id=payload.product_id,
        user_id=current_user.id,
        movement_type=payload.movement_type,
        quantity=payload.quantity,
        previous_qty=previous_qty,
        new_qty=new_qty,
        reference=payload.reference,
        notes=payload.notes,
    )
    db.add(movement)

    db.commit()
    db.refresh(movement)
    return movement