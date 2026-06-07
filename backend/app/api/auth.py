from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import AVATAR_UPLOAD_DIR, BASE_URL
from app.core.database import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_email_change_token,
    decode_token,
    decode_email_change_token,
)
from app.models.user import User
from app.schemas.auth import (
    UserCreate,
    LoginRequest,
    UserResponse,
    Token,
    ProfileUpdate,
    RequestEmailChange,
    ChangePassword,
)
from app.services.email import send_email_change_email

router = APIRouter()
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User | None:
    """Return current user if Bearer token is valid; else None."""
    if not credentials:
        return None
    payload = decode_token(credentials.credentials)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    return db.query(User).filter(User.username == username).first()


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return current authenticated user (for profile)."""
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update first name and last name."""
    if body.first_name is not None:
        current_user.first_name = body.first_name.strip() or None
    if body.last_name is not None:
        current_user.last_name = body.last_name.strip() or None
    db.commit()
    db.refresh(current_user)
    return current_user


ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_AVATAR_BYTES = 3 * 1024 * 1024  # 3 MB


@router.post("/avatar", response_model=UserResponse)
def upload_avatar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    """Upload profile avatar image. Replaces existing."""
    if file.content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, or WebP images are allowed.",
        )
    AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".jpg" if file.content_type == "image/jpeg" else ".png" if file.content_type == "image/png" else ".webp"
    path = AVATAR_UPLOAD_DIR / f"{current_user.id}{ext}"
    try:
        with path.open("wb") as f:
            size = 0
            for chunk in file.file:
                size += len(chunk)
                if size > MAX_AVATAR_BYTES:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large (max 3 MB).")
                f.write(chunk)
    finally:
        file.file.close()
    for old in AVATAR_UPLOAD_DIR.glob(f"{current_user.id}.*"):
        if old != path:
            try:
                old.unlink(missing_ok=True)
            except OSError:
                pass
    current_user.avatar_url = f"/api/auth/avatar/{current_user.id}"
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/avatar/{user_id}")
def get_avatar(user_id: int, db: Session = Depends(get_db)):
    """Serve avatar image for user (no auth required for display)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.avatar_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = AVATAR_UPLOAD_DIR / f"{user_id}{ext}"
        if p.exists():
            return FileResponse(p, media_type=f"image/{ext[1:]}" if ext != ".jpg" else "image/jpeg")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar file not found")


@router.post("/request-email-change")
def request_email_change(
    body: RequestEmailChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send confirmation link to new address."""
    if db.query(User).filter(User.email == body.new_email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use.")
    token = create_email_change_token(username=current_user.username, new_email=body.new_email)
    confirm_url = f"{BASE_URL.rstrip('/')}/profile?confirm_email={token}"
    try:
        send_email_change_email(to_new_email=body.new_email, confirm_url=confirm_url, username=current_user.username)
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to send email")
    return {"message": "Confirmation link sent to your new email. Check your inbox."}


@router.get("/confirm-email-change")
def confirm_email_change(token: str, db: Session = Depends(get_db)):
    """Confirm new email from link (token in query)."""
    payload = decode_email_change_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link.")
    username = payload.get("sub")
    new_email = payload.get("new_email")
    if not username or not new_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if db.query(User).filter(User.email == new_email).filter(User.id != user.id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use.")
    user.email = new_email
    user.email_verified = True
    db.commit()
    return {"message": "Email updated successfully."}


@router.post("/change-password")
def change_password(
    body: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change password using current password."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    current_user.password_hash = get_password_hash(body.new_password)
    db.commit()
    return {"message": "Password updated successfully."}


@router.post("/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user_in.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = User(
        username=user_in.username,
        email=user_in.email,
        email_verified=True,
        password_hash=get_password_hash(user_in.password),
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is busy. Please try again.")
    return user


@router.post("/login", response_model=Token)
def login(user_in: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == user_in.username).first()
    if not user or not verify_password(user_in.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username})
    return Token(access_token=access_token, user=UserResponse.model_validate(user))
