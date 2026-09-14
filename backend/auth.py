from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.database import engine
from backend.models import User
from backend.security import (
    verify_password,
    create_access_token,
)
from backend.dependencies import get_current_user


router = APIRouter(
    prefix="/auth",
    tags=["Autenticación"]
)


def get_db():
    with Session(engine) as session:
        yield session


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.email == form_data.username
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Email o contraseña incorrectos"
        )

    if not user.active:
        raise HTTPException(
            status_code=403,
            detail="El usuario está desactivado"
        )

    if not verify_password(
        form_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Email o contraseña incorrectos"
        )

    access_token = create_access_token(
        user_id=user.id,
        company_id=user.company_id
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "company_id": user.company_id,
            "role": user.role,
        }
    }


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "company_id": current_user.company_id,
        "role": current_user.role,
    }