import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, InvalidName


@asynccontextmanager
async def lifespan(app: FastAPI):
    uri = os.getenv("MONGO_URI")
    nombre_db = os.getenv("MONGO_DB", "conectasocial_db")
    if not uri:
        raise RuntimeError("Configura MONGO_URI antes de iniciar la API.")

    try:
        cliente = MongoClient(uri, serverSelectionTimeoutMS=3000)
    except (ConfigurationError, ValueError):
        raise RuntimeError("Revisa el formato de MONGO_URI.") from None

    with cliente:
        try:
            app.state.publicaciones = cliente[nombre_db]["publicaciones"]
        except InvalidName:
            raise RuntimeError("Revisa el nombre indicado en MONGO_DB.") from None
        yield
