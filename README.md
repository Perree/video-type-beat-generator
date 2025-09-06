# Type Beat Video Generator

Una aplicación de escritorio para automatizar la generación de videos de type beats para YouTube en formato horizontal 16:9.

## Características

- Carga de beats (archivos .wav, .mp3) en lote
- Asignación de géneros a cada beat
- Gestión de imágenes por género
- Generación automática de videos MP4 (1920x1080)
- Organización de videos por género
- Interfaz gráfica intuitiva

## Requisitos

- Python 3.x
- PyQt5 (se instalará automáticamente)
- FFmpeg (incluido en la carpeta bin)

## Instalación

1. Clona o descarga este repositorio
2. Asegúrate de tener Python 3.x instalado
3. Las dependencias se instalarán automáticamente al iniciar la aplicación

Nota: FFmpeg ya está incluido en la carpeta bin del proyecto, por lo que no es necesario instalarlo por separado.

## Estructura de carpetas

- `/beats`: Carpeta para los archivos de audio
- `/images/{genero}`: Carpetas para imágenes organizadas por género
- `/exported_videos`: Carpeta donde se guardan los videos generados
- `/config`: Archivos de configuración de la aplicación

## Uso

### Windows:
- Ejecuta `start_app.bat`

### Otras plataformas:
- Ejecuta `python main.py`

## Flujo de trabajo

1. Carga tus beats utilizando el botón "Cargar Beats"
2. Selecciona uno o varios beats de la lista
3. Selecciona un género del desplegable (o crea uno nuevo)
4. Haz clic en "Asignar a Seleccionados"
5. Si es necesario, añade imágenes al género mediante "Gestionar Géneros"
6. Repite los pasos 2-4 para todos los beats que desees procesar
7. Selecciona la carpeta de salida (opcional)
8. Haz clic en "Generar Videos"

## Notas importantes

- Cada beat debe tener un género asignado
- Cada género debe tener al menos una imagen
- Si hay más beats que imágenes en un género, la aplicación reutilizará imágenes

## Licencia

Este proyecto está licenciado bajo MIT License.
