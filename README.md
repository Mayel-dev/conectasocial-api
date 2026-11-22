# ConectaSocial · API REST para la PC4

Postman envía solicitudes HTTP a FastAPI en AppTier. Pydantic valida los datos y PyMongo ejecuta el CRUD sobre la colección `conectasocial_db.publicaciones` de la PC3. MongoDB conserva el `_id` como `ObjectId` y la API lo entrega en JSON como texto de 24 caracteres hexadecimales.

## Construir la imagen

Desde la carpeta que contiene el `Dockerfile`, ejecuta los siguientes comandos. En Ubuntu Server 24.04 LTS necesitas Docker Engine y acceso al daemon. Si tu cuenta lo requiere, antepone `sudo` a los comandos `docker`. [Instalación oficial de Docker en Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

```bash
docker version
docker build -t conectasocial-api:pc4 .
```

## Probar en local con MongoDB 7.0

Ejecuta cada comando en una terminal. Los dos contenedores comparten una red Docker y la API usa el nombre del contenedor de MongoDB como servidor. La base de prueba se llama `conectasocial_pruebas`. Solo el puerto HTTP se publica en tu equipo.

```bash
docker network create conectasocial-pc4-local
docker run -d --rm --name pc4-mongo-local --network conectasocial-pc4-local mongo:7.0
docker run -d --rm --name pc4-api-local --network conectasocial-pc4-local -p 127.0.0.1:8000:8000 -e MONGO_URI=mongodb://pc4-mongo-local:27017/ -e MONGO_DB=conectasocial_pruebas conectasocial-api:pc4
curl -i http://127.0.0.1:8000/publicaciones
```

Cuando MongoDB esté listo, la consulta inicial devolverá `200` y `[]`. Abre la documentación interactiva o sigue la secuencia de Postman de abajo. [Swagger local](http://127.0.0.1:8000/docs)

Al terminar las pruebas, estos comandos eliminan los contenedores temporales, sus datos de prueba y la red.

```bash
docker stop pc4-api-local pc4-mongo-local
docker network rm conectasocial-pc4-local
```

## Conectar AppTier con DataTier en EC2

1. Coloca ambas instancias en la misma VPC con conectividad por IP privada. Asigna un grupo de seguridad dedicado a AppTier y otro a DataTier. En el grupo de DataTier, configura la entrada **TCP 27017 con el ID del grupo de AppTier como único origen**. Revisa todos los grupos asociados a DataTier y elimina cualquier entrada más amplia para ese puerto, incluidas `0.0.0.0/0` y `::/0`. Si restringiste la salida de AppTier, permite TCP 27017 hacia el grupo de DataTier. [Referencias entre grupos de seguridad de AWS](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)
2. En DataTier, comprueba con `docker ps` que el puerto 27017 del contenedor de la PC3 está publicado en la IP privada de la instancia. Un mapeo apropiado es `-p IP_PRIVADA_DATATIER:27017:27017`. Usa la base y el volumen existentes de la PC3. La consulta desde AppTier del paso 4 comprueba que MongoDB acepta conexiones por esa ruta. [Puertos publicados en Docker](https://docs.docker.com/engine/network/port-publishing/)
3. En AppTier, construye la imagen como se indica arriba. Crea el archivo de configuración con permisos de lectura y escritura solo para tu usuario.

   ```bash
   install -m 600 .env.example .env
   nano .env
   ```

   Reemplaza los marcadores en tu copia local. Usa la **IP privada de DataTier** y un usuario con permiso de lectura y escritura en `conectasocial_db`. `authSource=admin` corresponde a un usuario creado en `admin`. Si se creó en otra base, indica esa base en `authSource`. Codifica los caracteres reservados del usuario o la contraseña en la URI, por ejemplo `@` como `%40`.

   ```ini
   MONGO_URI=mongodb://USUARIO:CONTRASENA@IP_PRIVADA_DATATIER:27017/?authSource=admin
   MONGO_DB=conectasocial_db
   ```

4. En AppTier, inicia la API y comprueba que responde con las publicaciones de la PC3. Docker carga las variables desde `.env` al crear el contenedor.

   ```bash
   docker run -d --name conectasocial-api --restart unless-stopped --env-file .env -p 127.0.0.1:8000:8000 conectasocial-api:pc4
   docker logs conectasocial-api
   curl -i http://127.0.0.1:8000/publicaciones
   ```

5. Para usar Postman desde tu equipo, habilita SSH (TCP 22) en AppTier desde tu IP y abre el siguiente túnel con tu clave y la dirección de AppTier. Mantén la sesión abierta. Uvicorn escucha en `0.0.0.0:8000` dentro del contenedor y el túnel llega al puerto publicado en el loopback de AppTier. Así puedes usar la misma URL de Postman con el puerto 8000 cerrado a Internet. Si hiciste la prueba local, detén esos contenedores antes de usar el mismo puerto.

   ```bash
   ssh -i clave-ec2.pem -N -L 8000:127.0.0.1:8000 ubuntu@IP_PUBLICA_APPTIER
   ```

## Verificar el CRUD desde Postman

Crea la variable `base_url` con el valor `http://127.0.0.1:8000`. Para POST y PUT selecciona **Body → raw → JSON** (`Content-Type: application/json`). Usa solo el identificador que obtengas al crear tu publicación de prueba.

| Paso | Método y URL | Qué comprobar |
| --- | --- | --- |
| 1 | POST `{{base_url}}/publicaciones` | Responde `201` con la publicación. Copia el valor de `_id` en una variable llamada `id`. |
| 2 | GET `{{base_url}}/publicaciones` | Responde `200` con una lista que contiene ese `_id`. |
| 3 | PUT `{{base_url}}/publicaciones/{{id}}` | Responde `200` con los cuatro campos actualizados y el mismo `_id`. |
| 4 | DELETE `{{base_url}}/publicaciones/{{id}}` | Responde `204` con cuerpo vacío. Repite el GET y comprueba que desapareció tu publicación. |

**Cuerpo para POST**

```json
{
  "usuario": "ana_pc4",
  "contenido": "Mi primera publicación desde Postman",
  "likes": 0,
  "estado": "activa"
}
```

**Cuerpo para PUT**

```json
{
  "usuario": "ana_pc4",
  "contenido": "Publicación editada desde Postman",
  "likes": 3,
  "estado": "editada"
}
```

Ambas operaciones requieren los cuatro campos. Los textos deben tener contenido y `likes` debe ser un entero JSON mayor o igual que cero dentro del rango de BSON. `estado` admite texto libre para conservar los valores usados en la PC3.

| Prueba | Respuesta esperada |
| --- | --- |
| DELETE con `abc` como ID | `400` por formato inválido. |
| Repetir DELETE con el ID que acabas de eliminar | `404` porque el documento ya no existe. |
| POST con `"likes": -1`, con un texto vacío o sin `usuario` | `422` con el campo que falló la validación. |
| GET mientras MongoDB está inaccesible | `503`. Revisa la IP privada, el puerto y los grupos de seguridad. |
| MongoDB rechaza la operación, por ejemplo por permisos | `500`. Revisa el usuario, `authSource` y sus permisos. |

## Archivos y decisiones

| Archivo | Función |
| --- | --- |
| `main.py` | Define las rutas, los modelos Pydantic y las respuestas HTTP. PUT usa `$set` para cambiar los cuatro campos en una sola operación y conservar cualquier otro campo de la PC3. |
| `database.py` | Lee las variables de entorno y comparte un `MongoClient` durante la vida de la aplicación. Las rutas reutilizan sus conexiones y el cliente se cierra al apagar Uvicorn. |
| `requirements.txt` | Fija las versiones de FastAPI, PyMongo, Pydantic y Uvicorn usadas en la imagen. |
| `Dockerfile` | Construye la imagen con Python 3.12 y ejecuta Uvicorn como usuario sin privilegios. |
| `.dockerignore` | Limita el contexto de construcción al código y sus dependencias. |
| `.gitignore` | Excluye credenciales locales, claves privadas y archivos generados por Python. |
| `.env.example` | Proporciona los nombres de las variables y marcadores para configurar cada entorno. |
| `README.md` | Reúne los pasos de construcción, conexión por red privada y prueba del CRUD. |
