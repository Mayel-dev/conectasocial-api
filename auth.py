import os
from time import time
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints


router = APIRouter(prefix="/auth", tags=["Autenticación"])
bearer = HTTPBearer(bearerFormat="JWT", auto_error=False)
hasher = PasswordHasher()


class Credenciales(BaseModel):
    model_config = ConfigDict(extra="forbid")
    usuario: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    contrasena: SecretStr = Field(min_length=1)


class TokenAcceso(BaseModel):
    access_token: str
    token_type: str = "bearer"


def configurar_jwt(app: FastAPI) -> None:
    clave = os.getenv("JWT_SECRET_KEY", "")
    if len(clave.strip().encode("utf-8")) < 32:
        raise RuntimeError("Configura JWT_SECRET_KEY con una clave aleatoria de al menos 32 bytes.")
    try:
        minutos = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
        if minutos < 1:
            raise ValueError
    except ValueError:
        raise RuntimeError("JWT_EXPIRE_MINUTES debe ser un entero positivo.") from None
    app.state.jwt_secret = clave
    app.state.jwt_minutos = minutos


def no_autorizado(detalle: str) -> HTTPException:
    return HTTPException(401, detalle, headers={"WWW-Authenticate": "Bearer"})


@router.post("/login")
def login(credenciales: Credenciales, request: Request) -> TokenAcceso:
    cuenta = request.app.state.usuarios.find_one({"usuario": credenciales.usuario})
    contrasena = credenciales.contrasena.get_secret_value()
    if cuenta is None:
        # Mantiene el coste de Argon2 también cuando el nombre no existe.
        hasher.hash(contrasena)
        raise no_autorizado("Credenciales incorrectas.")
    try:
        hasher.verify(cuenta["contrasena_hash"], contrasena)
    except (VerificationError, InvalidHashError):
        raise no_autorizado("Credenciales incorrectas.") from None

    token = jwt.encode(
        {"sub": str(cuenta["_id"]), "exp": int(time()) + request.app.state.jwt_minutos * 60},
        request.app.state.jwt_secret,
        algorithm="HS256",
    )
    return TokenAcceso(access_token=token)


def usuario_actual(
    request: Request,
    credencial: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credencial is None:
        raise no_autorizado("Se requiere un token Bearer.")
    try:
        datos = jwt.decode(
            credencial.credentials,
            request.app.state.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        usuario_id = ObjectId(datos["sub"])
    except (jwt.InvalidTokenError, InvalidId, TypeError):
        raise no_autorizado("Token inválido o expirado.") from None

    cuenta = request.app.state.usuarios.find_one({"_id": usuario_id}, {"usuario": 1})
    if cuenta is None:
        raise no_autorizado("El usuario del token ya no existe.")
    return cuenta["usuario"]


UsuarioActual = Annotated[str, Depends(usuario_actual)]
