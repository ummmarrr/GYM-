from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db import AuditEvent, Role, User, get_db
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


def _issue(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        role=user.role.value,
        full_name=user.full_name,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Annotated[Session, Depends(get_db)]):
    """Public self-signup. Always creates a member; staff roles are granted by an admin."""
    email = str(payload.email).lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=Role.MEMBER,
    )
    db.add(user)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="account.self_registered",
            resource_type="user",
            resource_id=user.id,
            detail=email,
        )
    )
    db.commit()
    return _issue(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.email == str(payload.email).lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        # Same message either way, so this cannot be used to discover valid emails.
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.active:
        raise HTTPException(status_code=403, detail="This account has been deactivated.")
    return _issue(user)


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
