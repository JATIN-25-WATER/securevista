from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    role: str
    display_name: str


class CurrentUser(BaseModel):
    id: str
    username: str
    role: str
    display_name: str

    class Config:
        from_attributes = True
