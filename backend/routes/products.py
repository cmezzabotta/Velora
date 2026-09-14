from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
)
from sqlalchemy.orm import Session

from ..database import engine
from ..models import Product, User
from ..dependencies import get_current_user

from openpyxl import load_workbook

import io
import re
import unicodedata


router = APIRouter(
    prefix="/products",
    tags=["Productos"]
)


def get_db():
    with Session(engine) as session:
        yield session


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalize_header(value):
    """
    Convierte encabezados diferentes en una forma comparable.

    Ejemplos:

    'Nombre del Producto' -> 'nombre del producto'
    'CÓDIGO_PRODUCTO'     -> 'codigo producto'
    ' Precio  '            -> 'precio'
    """

    if value is None:
        return ""

    value = str(value).strip().lower()

    value = unicodedata.normalize(
        "NFD",
        value
    )

    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Mn"
    )

    value = value.replace("_", " ")
    value = value.replace("-", " ")

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ============================================================
# CAMPOS RECONOCIDOS
# ============================================================

FIELD_PRIORITIES = {

    "name": [
        # Español
        "nombre",
        "nombre producto",
        "nombre del producto",
        "nombre articulo",
        "nombre del articulo",
        "producto",
        "articulo",
        "artículo",
        "item",
        "ítem",
        "elemento",
        "descripcion del producto",
        "denominacion",
        "denominación",
        "nombre comercial",
        "nombre producto comercial",
        "producto nombre",

        # Inglés
        "name",
        "product name",
        "item name",
        "article name",
        "product",
        "item",
        "article",
        "product description",
        "product title",
        "title",
        "description",
        "product label",
        "product designation",
    ],

    "sku": [
        # Español
        "sku",
        "codigo",
        "código",
        "codigo producto",
        "código producto",
        "codigo del producto",
        "código del producto",
        "codigo de producto",
        "código de producto",
        "codigo articulo",
        "código artículo",
        "codigo del articulo",
        "código del artículo",
        "codigo interno",
        "código interno",
        "cod",
        "cod.",
        "referencia",
        "ref",
        "referencia producto",
        "numero de producto",
        "número de producto",
        "id producto",
        "identificador",
        "identificador producto",

        # Inglés
        "sku",
        "product sku",
        "item sku",
        "stock keeping unit",
        "code",
        "product code",
        "item code",
        "article code",
        "internal code",
        "internal reference",
        "reference",
        "product reference",
        "item reference",
        "ref",
        "product id",
        "item id",
        "article id",
        "identifier",
        "product identifier",
        "barcode",
        "bar code",
        "ean",
        "upc",
    ],

    "description": [
        # Español
        "descripcion",
        "descripción",
        "descripcion del producto",
        "descripción del producto",
        "descripcion producto",
        "descripción producto",
        "descripcion corta",
        "descripción corta",
        "descripcion larga",
        "descripción larga",
        "detalle",
        "detalle del producto",
        "detalle producto",
        "informacion",
        "información",
        "informacion del producto",
        "información del producto",
        "observaciones",
        "comentarios",
        "caracteristicas",
        "características",
        "especificaciones",
        "especificacion",
        "especificación",
        "notas",

        # Inglés
        "description",
        "product description",
        "item description",
        "article description",
        "short description",
        "long description",
        "details",
        "product details",
        "item details",
        "information",
        "product information",
        "notes",
        "comments",
        "characteristics",
        "features",
        "specifications",
        "specification",
        "product features",
        "additional information",
    ],

    "price": [
        # Español
        "precio",
        "precio de venta",
        "precio venta",
        "precio unitario",
        "precio final",
        "precio lista",
        "precio de lista",
        "precio publico",
        "precio público",
        "precio minorista",
        "precio mayorista",
        "valor",
        "valor de venta",
        "valor venta",
        "valor unitario",
        "importe",
        "importe unitario",
        "costo",
        "coste",
        "precio producto",
        "precio articulo",
        "precio artículo",
        "valor producto",

        # Inglés
        "price",
        "product price",
        "item price",
        "unit price",
        "sale price",
        "selling price",
        "sales price",
        "retail price",
        "wholesale price",
        "list price",
        "price list",
        "final price",
        "amount",
        "unit amount",
        "value",
        "unit value",
        "cost",
        "unit cost",
        "product cost",
        "item cost",
        "msrp",
        "recommended retail price",
        "rrp",
    ],

    "stock": [
        # Español
        "stock",
        "stock disponible",
        "existencia",
        "existencias",
        "cantidad",
        "cantidad disponible",
        "unidades",
        "unidades disponibles",
        "inventario",
        "inventario disponible",
        "disponible",
        "cantidad en stock",
        "saldo",
        "disponibilidad",
        "cantidad producto",
        "cantidad de productos",
        "cantidad articulo",
        "cantidad artículo",
        "unidades en stock",
        "stock actual",
        "existencia actual",

        # Inglés
        "stock",
        "stock quantity",
        "stock level",
        "inventory",
        "inventory quantity",
        "inventory level",
        "available stock",
        "available quantity",
        "quantity",
        "quantity available",
        "units",
        "units available",
        "units in stock",
        "on hand",
        "quantity on hand",
        "stock on hand",
        "current stock",
        "current inventory",
        "availability",
        "available",
        "product quantity",
        "item quantity",
        "article quantity",
    ],
}


FIELD_LABELS = {
    "name": "Nombre",
    "sku": "SKU",
    "description": "Descripción",
    "price": "Precio",
    "stock": "Stock",
}


# ============================================================
# DETECCIÓN INTELIGENTE DE COLUMNAS
# ============================================================

def detect_columns(headers):
    """
    Detecta qué columna del Excel corresponde a cada campo
    de Velora.

    La prioridad es:

    1. coincidencia exacta
    2. coincidencia normalizada
    3. coincidencia flexible

    Además evita utilizar una misma columna para dos campos.
    """

    normalized_headers = [
        normalize_header(header)
        for header in headers
    ]

    used_indexes = set()
    mapping = {}

    for field, priorities in FIELD_PRIORITIES.items():

        # ----------------------------------------------------
        # PRIMERA PRIORIDAD: coincidencia exacta
        # ----------------------------------------------------

        found = None

        for priority_index, candidate in enumerate(priorities):

            candidate_normalized = normalize_header(
                candidate
            )

            for index, normalized_header in enumerate(
                normalized_headers
            ):

                if index in used_indexes:
                    continue

                if normalized_header == candidate_normalized:

                    found = {
                        "index": index,
                        "header": headers[index],
                        "confidence": (
                            100
                            if priority_index == 0
                            else max(
                                70,
                                99 - priority_index * 3
                            )
                        ),
                    }

                    break

            if found:
                break

        # ----------------------------------------------------
        # SEGUNDA PRIORIDAD: coincidencia flexible
        # ----------------------------------------------------

        if found is None:

            for priority_index, candidate in enumerate(
                priorities
            ):

                candidate_normalized = normalize_header(
                    candidate
                )

                for index, normalized_header in enumerate(
                    normalized_headers
                ):

                    if index in used_indexes:
                        continue

                    if (
                        candidate_normalized
                        and candidate_normalized
                        in normalized_header
                    ):

                        found = {
                            "index": index,
                            "header": headers[index],
                            "confidence": max(
                                60,
                                88 - priority_index * 4
                            ),
                        }

                        break

                if found:
                    break

        # ----------------------------------------------------
        # GUARDAR RESULTADO
        # ----------------------------------------------------

        if found:

            used_indexes.add(
                found["index"]
            )

            mapping[field] = found

    return mapping


# ============================================================
# CONVERSIÓN DE VALORES
# ============================================================

def clean_string(value):

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def clean_number(value):

    if value is None:
        return 0

    if isinstance(value, (int, float)):
        return float(value)

    value = str(value).strip()

    if not value:
        return 0

    # Elimina símbolos monetarios
    value = value.replace("$", "")
    value = value.replace("€", "")
    value = value.replace("ARS", "")
    value = value.replace("USD", "")

    value = value.strip()

    # Formato argentino:
    # 1.250,50 -> 1250.50

    if "," in value and "." in value:

        value = value.replace(
            ".",
            ""
        )

        value = value.replace(
            ",",
            "."
        )

    elif "," in value:

        value = value.replace(
            ",",
            "."
        )

    try:

        return float(value)

    except ValueError:

        return 0


# ============================================================
# OBTENER PRODUCTOS
# ============================================================

@router.get("")
def get_products(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    products = (
        db.query(Product)
        .filter(
            Product.company_id == current_user.company_id,
            Product.active == True
        )
        .order_by(Product.name.asc())
        .all()
    )

    return [
        {
            "id": product.id,
            "company_id": product.company_id,
            "name": product.name,
            "sku": product.sku,
            "description": product.description,
            "price": float(product.price),
            "stock": float(product.stock),
            "active": product.active,
        }
        for product in products
    ]


# ============================================================
# ANALIZAR EXCEL
# ============================================================

@router.post("/import/analyze")
async def analyze_products_excel(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No se recibió ningún archivo."
        )

    filename = file.filename.lower()

    if not filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser un Excel .xlsx"
        )

    try:

        contents = await file.read()

        workbook = load_workbook(
            filename=io.BytesIO(contents),
            read_only=True,
            data_only=True
        )

    except Exception as error:

        raise HTTPException(
            status_code=400,
            detail=f"No se pudo leer el Excel: {error}"
        )

    # ========================================================
    # BUSCAR LA PRIMERA HOJA CON DATOS
    # ========================================================

    worksheet = None

    for sheet in workbook.worksheets:

        rows = sheet.iter_rows(
            values_only=True
        )

        first_row = next(
            rows,
            None
        )

        if first_row:

            worksheet = sheet
            break

    if worksheet is None:

        raise HTTPException(
            status_code=400,
            detail="El Excel no contiene datos."
        )

    rows = list(
        worksheet.iter_rows(
            values_only=True
        )
    )

    if len(rows) < 2:

        raise HTTPException(
            status_code=400,
            detail="El Excel debe contener encabezados y al menos un producto."
        )

    # ========================================================
    # ENCABEZADOS
    # ========================================================

    headers = list(
        rows[0]
    )

    mapping = detect_columns(
        headers
    )

    # ========================================================
    # PRODUCTOS
    # ========================================================

    products = []

    for row_number, row in enumerate(
        rows[1:],
        start=2
    ):

        if not any(
            value is not None
            for value in row
        ):
            continue

        def get_value(field):

            if field not in mapping:
                return None

            index = mapping[field]["index"]

            if index >= len(row):
                return None

            return row[index]

        name = clean_string(
            get_value("name")
        )

        sku = clean_string(
            get_value("sku")
        )

        description = clean_string(
            get_value("description")
        )

        price = clean_number(
            get_value("price")
        )

        stock = clean_number(
            get_value("stock")
        )

        # Si no hay nombre, la fila necesita revisión.
        valid = bool(name)

        products.append(
            {
                "temporary_id": row_number,
                "name": name or "",
                "sku": sku or "",
                "description": description or "",
                "price": price,
                "stock": stock,
                "valid": valid,
            }
        )

    # ========================================================
    # COLUMNAS UTILIZADAS
    # ========================================================

    used_indexes = {
        value["index"]
        for value in mapping.values()
    }

    recognized_columns = []

    for field, info in mapping.items():

        recognized_columns.append(
            {
                "excel_column": info["header"],
                "velora_field": FIELD_LABELS[field],
                "field": field,
                "confidence": info["confidence"],
            }
        )

    additional_columns = []

    for index, header in enumerate(headers):

        if index not in used_indexes:

            additional_columns.append(
                str(header)
                if header is not None
                else ""
            )

    return {
        "filename": file.filename,
        "sheet": worksheet.title,

        "total_products": len(products),

        "recognized_columns":
            recognized_columns,

        "additional_columns":
            additional_columns,

        "products":
            products,
    }


# ============================================================
# IMPORTACIÓN MASIVA
# ============================================================

@router.post("/import")
def import_products(
    products: list[dict],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if not products:

        raise HTTPException(
            status_code=400,
            detail="No hay productos para importar."
        )

    imported = []

    for product_data in products:

        name = clean_string(
            product_data.get("name")
        )

        if not name:
            continue

        new_product = Product(
            company_id=current_user.company_id,
            name=name,
            sku=clean_string(
                product_data.get("sku")
            ),
            description=clean_string(
                product_data.get("description")
            ),
            price=clean_number(
                product_data.get("price")
            ),
            stock=clean_number(
                product_data.get("stock")
            ),
            active=True,
        )

        db.add(
            new_product
        )

        imported.append(
            new_product
        )

    db.commit()

    for product in imported:

        db.refresh(
            product
        )

    return {
        "message": "Productos importados correctamente.",
        "count": len(imported),
        "products": [
            {
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "description": product.description,
                "price": float(product.price),
                "stock": float(product.stock),
                "active": product.active,
            }
            for product in imported
        ],
    }


# ============================================================
# ACTUALIZAR PRODUCTO
# ============================================================

@router.put("/{product_id}")
def update_product(
    product_id: int,
    product_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.company_id == current_user.company_id,
            Product.active == True
        )
        .first()
    )

    if not product:

        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado"
        )

    product.name = product_data.get(
        "name",
        product.name
    )

    product.sku = product_data.get(
        "sku"
    )

    product.description = product_data.get(
        "description"
    )

    product.price = product_data.get(
        "price",
        product.price
    )

    product.stock = product_data.get(
        "stock",
        product.stock
    )

    db.commit()
    db.refresh(product)

    return {
        "id": product.id,
        "company_id": product.company_id,
        "name": product.name,
        "sku": product.sku,
        "description": product.description,
        "price": float(product.price),
        "stock": float(product.stock),
        "active": product.active,
    }


# ============================================================
# ELIMINAR PRODUCTO
# ============================================================

@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.company_id == current_user.company_id,
            Product.active == True
        )
        .first()
    )

    if not product:

        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado"
        )

    product.active = False

    db.commit()

    return {
        "message": "Producto eliminado correctamente"
    }