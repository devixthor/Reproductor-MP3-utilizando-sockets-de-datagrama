# Reproductor MP3 por sockets UDP

Cliente y servidor de reproducción/descarga de archivos MP3 mediante UDP, con transferencia Go-Back-N.

## Requisitos

- Windows y Python 3.10 o posterior.
- Las dependencias declaradas en `requirements.txt`.
- La reproducción integrada usa pygame para reproducir MP3 dentro de la aplicación y controlar reproducción, pausa y detención.
- Archivos MP3 propios en la carpeta `Reproductor/Archivos/catalogo_servidor`.

## Preparar el entorno

Desde la carpeta principal del proyecto, crea el entorno virtual e instala las dependencias:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

En instalaciones donde el entorno virtual use la carpeta `bin` en lugar de `Scripts`, usa:

```powershell
.\.venv\bin\python.exe -m pip install -r requirements.txt
```

En VS Code, selecciona como intérprete el Python dentro de `.venv` (`Scripts\python.exe` o `bin\python.exe`, según corresponda).

Si usas Python de MSYS2 UCRT64 en Windows, instala pygame desde una terminal UCRT64 con `pacman -S mingw-w64-ucrt-x86_64-python-pygame` y crea el entorno virtual con `python -m venv --system-site-packages .venv`. El entorno virtual debe heredar los paquetes de MSYS2 para poder cargar pygame y sus bibliotecas SDL.

## Agregar música

Coloca archivos `.mp3` en `Reproductor/Archivos/catalogo_servidor`. El servidor lee sus etiquetas ID3 para mostrar título y artista. Las carpetas del catálogo y las descargas se crean automáticamente y están excluidas de Git.

La descarga opcional desde Jamendo requiere un identificador de API. En PowerShell, configúralo antes de iniciar el servidor:

```powershell
$env:JAMENDO_CLIENT_ID = "tu_client_id"
```

Sin esta variable, el servidor usa los archivos locales.

## Ejecutar en una computadora

Abre dos terminales en la carpeta principal del proyecto.

Terminal 1:

```powershell
.\.venv\Scripts\python.exe .\Reproductor\Archivos\servidor.py
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe .\Reproductor\Archivos\cliente.py
```

Si el entorno usa `bin`, reemplaza `Scripts\python.exe` por `bin\python.exe`. La interfaz organiza la biblioteca por género (ID3 o etiquetas de Jamendo), permite filtrar por título/artista y reproduce las pistas dentro de la aplicación. Incluye controles de pista anterior/siguiente, pausa, detención, búsqueda de posición, volumen y reproducción continua. El cliente guarda las descargas en `Reproductor/Archivos/descargas_cliente`.

## Ejecutar en dos computadoras

El valor inicial `127.0.0.1` solo permite conexiones desde la misma computadora. Para conectarse por la red local, cambia `SERVER_IP` en `servidor.py` por `0.0.0.0` y `SERVER_ADDR` en `cliente.py` por la dirección IP local del servidor. Permite el tráfico UDP por el puerto `9999` en el firewall del servidor.
