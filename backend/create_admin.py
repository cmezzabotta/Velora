from sqlalchemy.orm import Session

from backend.database import engine
from backend.models import Company, User
from backend.security import hash_password


COMPANY_ID = 1

ADMIN_NAME = "Administrador Demo"
ADMIN_EMAIL = "admin@velora.test"
ADMIN_PASSWORD = "VeloraDemo123!"


with Session(engine) as session:

    company = session.get(
        Company,
        COMPANY_ID
    )

    if not company:
        raise RuntimeError(
            f"No existe la empresa con ID {COMPANY_ID}"
        )

    existing_user = session.query(User).filter(
        User.email == ADMIN_EMAIL
    ).first()

    if existing_user:
        print("El usuario administrador ya existe.")

    else:

        user = User(
            company_id=company.id,
            name=ADMIN_NAME,
            email=ADMIN_EMAIL,
            password_hash=hash_password(
                ADMIN_PASSWORD
            ),
            role="admin",
            active=True,
        )

        session.add(user)
        session.commit()

        print("Usuario administrador creado correctamente.")
        print(f"Email: {ADMIN_EMAIL}")
        print(f"Contraseña: {ADMIN_PASSWORD}")