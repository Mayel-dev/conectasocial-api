# ConectaSocial · API REST para el TB2

La API de la PC4 conserva el CRUD de `conectasocial_db.publicaciones`. Para el TB2 añade autenticación mediante tokens JWT y una colección `usuarios`. Cualquier usuario autenticado puede consultar las publicaciones y crear las suyas. Solo el propietario puede editar o eliminar una publicación.

El login verifica la contraseña con Argon2id. El JWT incluye el `_id` de la cuenta en `sub` y su vencimiento en `exp`. En cada solicitud protegida, FastAPI valida la firma HS256 y la expiración, y busca en MongoDB el nombre de esa cuenta. El cliente recibe el `_id` de cada publicación como texto. [Verificación con Argon2](https://argon2-cffi.readthedocs.io/en/stable/api.html) · [Expiración en PyJWT](https://pyjwt.readthedocs.io/en/stable/usage.html#expiration-time-claim-exp)

## Construir la imagen

Los comandos usan Bash y se ejecutan desde la carpeta que contiene el `Dockerfile`. En Ubuntu Server 24.04 LTS necesitas Docker Engine y acceso al daemon. Si tu cuenta lo requiere, antepone `sudo` a los comandos `docker`. [Instalación oficial de Docker en Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

```bash
docker version
docker build -t conectasocial-api:tb2 .
```

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `MONGO_URI` | Obligatoria. URI de la instancia MongoDB. En EC2 usa la IP privada de DataTier. |
| `MONGO_DB` | Nombre de la base. Por defecto, `conectasocial_db`. |
| `JWT_SECRET_KEY` | Obligatoria. Clave aleatoria de al menos 32 bytes, exclusiva de cada entorno. |
| `JWT_EXPIRE_MINUTES` | Duración del token en minutos. Acepta enteros positivos y vale `60` por defecto. |

Genera la clave con `openssl rand -hex 32` y guarda el resultado en el archivo de entorno privado. Conserva esa clave entre reinicios. Si la cambias, los usuarios tendrán que iniciar sesión de nuevo. Git excluye `.env` y `.env.local`. La opción `--env-file` indica a Docker cuál cargar al crear el contenedor.

## Probar en local con MongoDB 7.0

Copia `.env.example` a `.env.local` para la primera ejecución. Edita esa copia con `MONGO_URI=mongodb://tb2-mongo-local:27017/`, `MONGO_DB=conectasocial_pruebas` y la clave JWT que generaste. Los contenedores compartirán una red Docker privada y solo el puerto HTTP se publicará en tu equipo.

```bash
docker network create conectasocial-tb2-local
docker run -d --rm --name tb2-mongo-local --network conectasocial-tb2-local mongo:7.0
docker run -d --rm --name tb2-api-local --network conectasocial-tb2-local --env-file .env.local -p 127.0.0.1:8000:8000 conectasocial-api:tb2
docker exec -it tb2-api-local python crear_usuarios.py
```

El script pide en la terminal una contraseña oculta para cada cuenta nueva, `ana_tb2` y `luis_tb2`. MongoDB genera sus identificadores, guarda el nombre y el hash en `usuarios` y aplica un índice único sobre `usuario`. Puedes repetir el comando si MongoDB tarda en iniciar o si falta una de las dos cuentas. Las cuentas existentes conservan su contraseña.

Al terminar las pruebas, estos comandos eliminan los contenedores temporales, sus datos de prueba y la red.

```bash
docker stop tb2-api-local tb2-mongo-local
docker network rm conectasocial-tb2-local
```

## Actualizar AppTier en EC2

1. Coloca ambas instancias en la misma VPC con conectividad por IP privada. Asigna un grupo de seguridad dedicado a AppTier y otro a DataTier. En el grupo de DataTier, configura la entrada **TCP 27017 con el ID del grupo de AppTier como único origen**. Revisa todos los grupos asociados a DataTier y elimina cualquier entrada más amplia para ese puerto, incluidas `0.0.0.0/0` y `::/0`. Si restringiste la salida de AppTier, permite TCP 27017 hacia el grupo de DataTier. [Referencias entre grupos de seguridad de AWS](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)
2. En DataTier, conserva la base y el volumen de la PC3. Comprueba con `docker ps` que MongoDB publica el puerto 27017 en la IP privada. En AppTier, coloca los archivos actualizados del TB2 en el directorio del backend y construye `conectasocial-api:tb2` con el comando anterior. Si ya publicaste esta versión en tu remoto, puedes actualizar la copia de trabajo limpia con `git pull --ff-only` antes de construir. [Puertos publicados en Docker](https://docs.docker.com/engine/network/port-publishing/)
3. **Conserva el `.env` de la PC4.** Añade `JWT_SECRET_KEY` y `JWT_EXPIRE_MINUTES=60` a ese archivo. En una instalación nueva, parte de la plantilla. El primer comando de abajo solo crea el archivo si todavía no existe.

   ```bash
   test -e .env || install -m 600 .env.example .env
   chmod 600 .env
   nano .env
   ```

   La cuenta técnica de `MONGO_URI` necesita acceso de lectura y escritura a `conectasocial_db` y permiso para crear el índice de `usuarios`. `authSource=admin` corresponde a una cuenta técnica creada en `admin`. Si se creó en otra base, indica esa base. Codifica los caracteres reservados de las credenciales en la URI, por ejemplo `@` como `%40`.

   ```ini
   MONGO_URI=mongodb://USUARIO:CONTRASENA@IP_PRIVADA_DATATIER:27017/?authSource=admin
   MONGO_DB=conectasocial_db
   ```

4. En AppTier, crea las cuentas de prueba desde la nueva imagen. Después sustituye el contenedor **de la API**. Estos comandos suponen que el contenedor de la PC4 se llama `conectasocial-api`. Puedes comprobarlo con `docker ps`. En una instalación nueva, omite `docker stop` y `docker rm`.

   ```bash
   docker run --rm -it --env-file .env conectasocial-api:tb2 python crear_usuarios.py
   docker stop conectasocial-api
   docker rm conectasocial-api
   docker run -d --name conectasocial-api --restart unless-stopped --env-file .env -p 127.0.0.1:8000:8000 conectasocial-api:tb2
   docker logs conectasocial-api
   curl -i http://127.0.0.1:8000/publicaciones
   ```

   Esa primera consulta debe responder `401`. Para comprobar también la conexión a DataTier, inicia sesión y ejecuta el GET con token como se indica más abajo.

5. Para usar Swagger o Postman desde tu equipo, permite SSH (TCP 22) en AppTier desde tu IP y abre este túnel. Mantén la sesión abierta. La API escucha en `0.0.0.0:8000` dentro del contenedor y Docker publica el puerto en el loopback de AppTier. Si usaste ese puerto para pruebas locales, libera el 8000 antes de abrir el túnel.

   ```bash
   ssh -i clave-ec2.pem -N -L 8000:127.0.0.1:8000 ubuntu@IP_PUBLICA_APPTIER
   ```

### Integración posterior con Nginx

El navegador accederá al frontend y a la API bajo el mismo origen HTTPS. Nginx terminará TLS y reenviará las solicitudes con la cabecera `Authorization: Bearer TOKEN`. Uvicorn sirve HTTP interno. Si Nginx se ejecuta en otra EC2, publica el 8000 en la IP privada de AppTier y limita su entrada al grupo de seguridad de Nginx. La configuración del certificado y la evidencia de HTTPS corresponden a esa etapa.

## Verificar el login y el CRUD

**1. Iniciar sesión.** En Postman usa `http://127.0.0.1:8000` como `base_url`. Envía `POST {{base_url}}/auth/login` con **Body → raw → JSON** y la contraseña que elegiste. También puedes ejecutar la misma petición en la documentación interactiva. [Swagger UI local](http://127.0.0.1:8000/docs)

```json
{
  "usuario": "ana_tb2",
  "contrasena": "<contraseña elegida en la terminal>"
}
```

Con credenciales válidas recibes `200` y un cuerpo de la forma `{"access_token":"<JWT>","token_type":"bearer"}`. Para las peticiones a `/publicaciones`, selecciona **Authorization → Bearer Token** en Postman o **Authorize** en Swagger UI. Pega solo el valor de `access_token`. Ambas herramientas añaden el prefijo `Bearer`.

**2. Crear y editar.** POST y PUT requieren los tres campos de este ejemplo. Para probar PUT, cambia `contenido` o `likes`. El servidor asigna `usuario` al crear la publicación y rechaza con `422` si lo incluyes en cualquiera de los dos cuerpos.

```json
{
  "contenido": "Mi primera publicación del TB2",
  "likes": 0,
  "estado": "activa"
}
```

| Paso | Solicitud y cuenta | Resultado esperado |
| --- | --- | --- |
| 1 | POST `/publicaciones` con el token de Ana | `201`. Guarda el `_id` y comprueba que `usuario` es `ana_tb2`. |
| 2 | GET `/publicaciones` con cualquiera de las cuentas | `200` con la publicación nueva y los documentos existentes. |
| 3 | PUT `/publicaciones/{id}` con el token de Ana y el cuerpo editado | `200` con los nuevos valores, el mismo `_id` y el mismo propietario. |
| 4 | Inicia sesión como `luis_tb2` y usa su token para PUT y DELETE sobre ese ID | Ambas solicitudes devuelven `403`. El documento conserva los valores del paso 3. |
| 5 | DELETE `/publicaciones/{id}` con el token de Ana | `204` con cuerpo vacío. Si repites la solicitud, recibes `404`. |

En PUT y DELETE sustituye `{id}` por el identificador de tu publicación de prueba. El backend compara el nombre de la cuenta exactamente con el campo `usuario` almacenado. Las publicaciones de la PC3 y PC4 se conservan tal como están. Un autor histórico sin cuenta coincidente sigue siendo visible en el listado y sus publicaciones quedan disponibles solo para consulta.

| Prueba | Respuesta esperada |
| --- | --- |
| Login con credenciales incorrectas o petición protegida con token ausente, inválido o expirado | `401` con cabecera `WWW-Authenticate: Bearer`. |
| DELETE con token válido y `abc` como ID | `400` por formato inválido. |
| POST con token válido y `"likes": -1`, texto vacío o sin `contenido` | `422` por datos inválidos. |
| Login con datos válidos o GET autenticado durante una caída de MongoDB | `503`. Revisa la IP privada, el puerto y los grupos de seguridad. |
| MongoDB rechaza la operación, por ejemplo por permisos | `500`. Revisa el usuario, `authSource` y sus permisos. |

## Archivos y decisiones

| Archivo | Función |
| --- | --- |
| `main.py` | Conserva el CRUD. En PUT y DELETE, MongoDB comprueba el ID y el propietario en la misma escritura. PUT modifica solo los tres campos editables. |
| `auth.py` | Valida credenciales, emite el JWT y resuelve la cuenta autenticada para las rutas protegidas. |
| `crear_usuarios.py` | Crea el índice único y las cuentas de prueba con hash Argon2id. Se ejecuta desde la terminal. |
| `database.py` | Abre la base configurada para la API y para el script. La API reutiliza su cliente durante la vida del proceso. |
| `requirements.txt` | Fija las versiones de las dependencias, incluidas PyJWT y argon2-cffi. |
| `Dockerfile` | Construye la imagen con Python 3.12 y ejecuta Uvicorn como usuario sin privilegios. |
| `.dockerignore` | Limita el contexto de construcción al código y sus dependencias. |
| `.gitignore` | Excluye credenciales locales, claves privadas y archivos generados por Python. |
| `.env.example` | Proporciona los nombres de las variables y marcadores para configurar cada entorno. |
| `README.md` | Reúne los pasos de construcción, conexión por red privada y prueba del CRUD. |
