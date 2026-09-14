from .database import engine, Base

from .models import (
    Company,
    Warehouse,
    Inventory,
    StockMovement,
)


print("Creando tablas de Velora...")

Base.metadata.create_all(bind=engine)

print("Tablas creadas correctamente.")