from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


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


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    username: str | None = None
