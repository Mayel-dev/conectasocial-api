import os
from contextlib import contextmanager

from pymongo import MongoClient
from pymongo.errors import ConfigurationError, InvalidName


@contextmanager
def abrir_base():
    uri = os.getenv("MONGO_URI")
    nombre_db = os.getenv("MONGO_DB", "conectasocial_db")
    if not uri:
        raise RuntimeError("Configura MONGO_URI para conectar con MongoDB.")

    try:
        cliente = MongoClient(uri, serverSelectionTimeoutMS=3000)
    except (ConfigurationError, ValueError):
        raise RuntimeError("Revisa el formato de MONGO_URI.") from None

    with cliente:
        try:
            base = cliente[nombre_db]
        except InvalidName:
            raise RuntimeError("Revisa el nombre indicado en MONGO_DB.") from None
        yield base
