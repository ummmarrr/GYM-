from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db import Role, User, get_db

bearer_scheme = HTTPBearer(auto_error=False)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Everything else a demo account posts would outlive the visit: deleted members, edited
# packages, removed documents. These two change nothing a later visitor would notice, and
# they are the whole point of the tour, so they stay open.
DEMO_WRITE_PATHS = ("/api/admin/analyst/ask",)
DEMO_WRITE_SUFFIXES = ("/book",)


def _user_from_credentials(
    credentials: HTTPAuthorizationCredentials | None, db: Session
) -> User | None:
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        return None
    user = db.get(User, payload.get("sub"))
    return user if user is not None and user.active else None


def is_demo_account(user: User) -> bool:
    """True for the shared logins advertised on the sign-in page."""
    return user.email.lower() in get_settings().demo_emails


def _guard_demo_account(user: User, request: Request) -> None:
    if request.method not in WRITE_METHODS:
        return
    if not is_demo_account(user):
        return
    path = request.url.path
    if path in DEMO_WRITE_PATHS or path.endswith(DEMO_WRITE_SUFFIXES):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "This is a shared demo login, so it can look at everything but change nothing. "
            "Create your own account to try this."
        ),
    )


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = _user_from_credentials(credentials, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please sign in to continue.",
        )
    _guard_demo_account(user, request)
    return user


def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """Used by FitBot, which must also serve signed-out visitors on the public site."""
    return _user_from_credentials(credentials, db)


def require_roles(*roles: Role):
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account does not have permission for this action.",
            )
        return user

    return dependency


require_admin = require_roles(Role.ADMIN)
require_staff = require_roles(Role.ADMIN, Role.TRAINER)
