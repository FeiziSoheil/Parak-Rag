from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str  # 6-digit numeric code


class UserResponse(BaseModel):
    id: int
    username: str
    email: str | None = None
    email_verified: bool = False
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None


class RequestEmailChange(BaseModel):
    new_email: EmailStr


class ConfirmPasswordChange(BaseModel):
    code: str
    new_password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    username: str | None = None
