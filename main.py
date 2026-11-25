from contextlib import asynccontextmanager
from typing import Annotated

from bson import ObjectId
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import ConnectionFailure, PyMongoError

import auth
from database import abrir_base


class Publicacion(BaseModel):
    contenido: str
    likes: int
    estado: str


class PublicacionEntrada(Publicacion):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, str_min_length=1)
    # BSON admite enteros con signo de hasta 64 bits.
    likes: int = Field(strict=True, ge=0, le=2**63 - 1)


class PublicacionSalida(Publicacion):
    usuario: str
    id: Annotated[str, BeforeValidator(str)] = Field(alias="_id")


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth.configurar_jwt(app)
    with abrir_base() as base:
        app.state.publicaciones = base["publicaciones"]
        app.state.usuarios = base["usuarios"]
        yield


app = FastAPI(title="ConectaSocial", version="2.0", lifespan=lifespan)
app.include_router(auth.router)


def convertir_id(id: str) -> ObjectId:
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "El id debe tener 24 caracteres hexadecimales.")
    return ObjectId(id)


def error_de_propiedad(publicaciones, publicacion_id: ObjectId) -> HTTPException:
    if publicaciones.find_one({"_id": publicacion_id}, {"_id": 1}) is None:
        return HTTPException(404, "Publicación inexistente.")
    return HTTPException(403, "Solo el propietario puede modificar o eliminar esta publicación.")


@app.exception_handler(RequestValidationError)
async def error_de_validacion(request: Request, exc: RequestValidationError):
    if request.scope.get("endpoint") is not auth.login:
        return await request_validation_exception_handler(request, exc)
    # FastAPI puede incluir el cuerpo completo del login en el campo "input".
    errores = [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errores})


@app.exception_handler(ConnectionFailure)
async def error_conexion(request: Request, exc: ConnectionFailure):
    return JSONResponse(status_code=503, content={"detail": "MongoDB no está disponible."})


@app.exception_handler(PyMongoError)
async def error_mongo(request: Request, exc: PyMongoError):
    return JSONResponse(status_code=500, content={"detail": "Falló la operación en MongoDB."})


@app.get(
    "/publicaciones", response_model=list[PublicacionSalida], dependencies=[Depends(auth.usuario_actual)]
)
def listar_publicaciones(request: Request):
    return list(request.app.state.publicaciones.find())


@app.post("/publicaciones", response_model=PublicacionSalida, status_code=status.HTTP_201_CREATED)
def crear_publicacion(publicacion: PublicacionEntrada, request: Request, usuario: auth.UsuarioActual):
    documento = {**publicacion.model_dump(), "usuario": usuario}
    resultado = request.app.state.publicaciones.insert_one(documento)
    return {**documento, "_id": resultado.inserted_id}


@app.put("/publicaciones/{id}", response_model=PublicacionSalida)
def modificar_publicacion(
    id: str, publicacion: PublicacionEntrada, request: Request, usuario: auth.UsuarioActual
):
    publicaciones = request.app.state.publicaciones
    publicacion_id = convertir_id(id)
    documento = publicaciones.find_one_and_update(
        {"_id": publicacion_id, "usuario": usuario},
        {"$set": publicacion.model_dump()},
        collation={"locale": "simple"},
        return_document=ReturnDocument.AFTER,
    )
    if documento is None:
        raise error_de_propiedad(publicaciones, publicacion_id)
    return documento


@app.delete("/publicaciones/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_publicacion(id: str, request: Request, usuario: auth.UsuarioActual) -> Response:
    publicaciones = request.app.state.publicaciones
    publicacion_id = convertir_id(id)
    resultado = publicaciones.delete_one(
        {"_id": publicacion_id, "usuario": usuario}, collation={"locale": "simple"}
    )
    if resultado.deleted_count == 0:
        raise error_de_propiedad(publicaciones, publicacion_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
