from getpass import getpass

from argon2 import PasswordHasher
from pymongo.errors import PyMongoError

from database import abrir_base


def crear_usuarios() -> None:
    hasher = PasswordHasher()
    with abrir_base() as base:
        usuarios = base["usuarios"]
        usuarios.create_index("usuario", unique=True)
        for nombre in ("ana_tb2", "luis_tb2"):
            filtro = {"usuario": nombre}
            if usuarios.find_one(filtro, {"_id": 1}) is not None:
                print(f"La cuenta {nombre} ya existe.")
                continue
            contrasena = getpass(f"Contraseña para {nombre}: ")
            if not contrasena:
                raise SystemExit("La contraseña debe tener al menos un carácter.")
            usuarios.update_one(
                filtro,
                {"$setOnInsert": {"contrasena_hash": hasher.hash(contrasena)}},
                upsert=True,
            )
            print(f"Cuenta {nombre} disponible.")


if __name__ == "__main__":
    try:
        crear_usuarios()
    except PyMongoError:
        raise SystemExit("MongoDB rechazó la operación. Revisa la conexión, los permisos y el índice único.") from None
