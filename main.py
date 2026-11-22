from typing import Annotated

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import ConnectionFailure, PyMongoError

from database import lifespan


class Publicacion(BaseModel):
    usuario: str
    contenido: str
    likes: int
    estado: str


class PublicacionEntrada(Publicacion):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, str_min_length=1)
    # BSON admite enteros con signo de hasta 64 bits.
    likes: int = Field(strict=True, ge=0, le=2**63 - 1)


class PublicacionSalida(Publicacion):
    id: Annotated[str, BeforeValidator(str)] = Field(alias="_id")


app = FastAPI(title="ConectaSocial", version="1.0", lifespan=lifespan)


def convertir_id(id: str) -> ObjectId:
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "El id debe tener 24 caracteres hexadecimales.")
    return ObjectId(id)


@app.exception_handler(ConnectionFailure)
async def error_conexion(request: Request, exc: ConnectionFailure):
    return JSONResponse(status_code=503, content={"detail": "MongoDB no está disponible."})


@app.exception_handler(PyMongoError)
async def error_mongo(request: Request, exc: PyMongoError):
    return JSONResponse(status_code=500, content={"detail": "Falló la operación en MongoDB."})


@app.get("/publicaciones", response_model=list[PublicacionSalida])
def listar_publicaciones(request: Request):
    return list(request.app.state.publicaciones.find())


@app.post("/publicaciones", response_model=PublicacionSalida, status_code=status.HTTP_201_CREATED)
def crear_publicacion(publicacion: PublicacionEntrada, request: Request):
    documento = publicacion.model_dump()
    resultado = request.app.state.publicaciones.insert_one(documento)
    return {**documento, "_id": resultado.inserted_id}


@app.put("/publicaciones/{id}", response_model=PublicacionSalida)
def modificar_publicacion(id: str, publicacion: PublicacionEntrada, request: Request):
    documento = request.app.state.publicaciones.find_one_and_update(
        {"_id": convertir_id(id)},
        {"$set": publicacion.model_dump()},
        return_document=ReturnDocument.AFTER,
    )
    if documento is None:
        raise HTTPException(404, "Publicación inexistente.")
    return documento


@app.delete("/publicaciones/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_publicacion(id: str, request: Request) -> Response:
    resultado = request.app.state.publicaciones.delete_one({"_id": convertir_id(id)})
    if resultado.deleted_count == 0:
        raise HTTPException(404, "Publicación inexistente.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
