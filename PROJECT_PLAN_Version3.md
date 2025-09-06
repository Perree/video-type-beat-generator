# Proyecto: Generador de Videos de Type Beats para YouTube

## Objetivo
Crear una app de escritorio que automatice la generación de videos de type beats para YouTube en formato largo (horizontal 16:9). El usuario podrá cargar audios en lote, asociar cada beat a un género, y la aplicación gestionará imágenes por género, asignando una imagen única y aleatoria a cada video.

---

## Requerimientos Funcionales

1. **Carga de Beats**
   - El usuario puede cargar entre 15 y 30 archivos de audio (.wav, .mp3) en lote.
   - Por cada beat, la app pregunta el género (ej: reggaetón, guitarra, trap, etc.).

2. **Gestión de Imágenes por Género**
   - La app permite precargar carpetas de imágenes asociadas a cada género.
   - Si el género seleccionado no tiene imágenes cargadas, la app debe pedir al usuario que suba imágenes para ese género (por ejemplo, 30 fotos de Pinterest).
   - Las imágenes se almacenan localmente y quedan disponibles para futuros usos.
   - Siempre debe existir la opción de agregar o eliminar imágenes por género desde la interfaz.

3. **Asignación Aleatoria de Imágenes**
   - Para cada beat en el lote, la app selecciona de forma aleatoria una imagen distinta del pack de imágenes del género (sin repeticiones dentro de un procesamiento).
   - Cada video generado tiene una imagen única, evitando duplicados en el mismo batch.

4. **Generación y Exportación Automática**
   - La app genera un video por beat, combinando audio + imagen, en formato MP4 (1920x1080, 16:9, imagen centrada, relleno negro si la imagen es vertical/cuadrada).
   - El nombre del video se genera automáticamente (por ejemplo, nombre del beat + género).
   - Los videos se exportan a una carpeta de salida, organizados por género.

5. **Procesamiento Batch**
   - El usuario puede procesar todos los beats en una sola tanda.
   - Se muestra una barra de progreso y avisos durante el proceso.

---

## Herramientas y Tecnologías

- **Python 3.x:** Lógica y automatización.
- **FFmpeg:** Procesamiento multimedia, ejecutado desde Python (subprocess).
- **PyQt5:** Interfaz gráfica de usuario (ventana, botones, drag & drop, gestión de imágenes por género).
- **Estructura de carpetas:**
  - `/beats`: Audios.
  - `/images/{genero}`: Imágenes por género.
  - `/exported_videos`: Videos generados.
  - `/config`: Configuración y presets.

---

## Flujo de Usuario

1. Abrir la app.
2. Cargar uno o varios audios en `/beats`.
3. Por cada beat, seleccionar el género.
4. Si no hay imágenes preexistentes para ese género, la app solicita cargarlas.
5. Las imágenes quedan guardadas en `/images/{genero}` para futuros usos.
6. Elegir carpeta de salida.
7. Presionar “Generar videos”.
8. Esperar a que finalice el procesamiento.
9. Recibir videos listos en `/exported_videos`, organizados por género.

---

## Lógica Principal del Script

- Recorrer todos los audios subidos.
- Para cada audio, preguntar el género.
- Verificar si existen imágenes para ese género:
  - Si no, pedir cargar imágenes y almacenarlas.
- Seleccionar aleatoriamente una imagen distinta para cada beat en el lote (sin repeticiones).
- Usar FFmpeg para generar el video:
  - Imagen centrada, relleno negro si es vertical/cuadrada.
  - Audio completo.
  - Exportar en MP4, 1920x1080.
- Guardar videos en la carpeta de salida, organizados por género.

---

## Script de Referencia (Python + FFmpeg)

```python
import os
import random
import subprocess

def get_images_for_genre(images_base_folder, genre):
    images_folder = os.path.join(images_base_folder, genre)
    return [os.path.join(images_folder, img) for img in os.listdir(images_folder) if img.endswith(('.jpg', '.png'))]

def generate_video(audio_path, image_path, output_path):
    cmd = [
        "ffmpeg",
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-vf", "scale=-1:1080,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264",
        "-preset", "fast",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]
    subprocess.run(cmd)

def process_beats(beats_folder, images_base_folder, output_folder, beats_info):
    # beats_info: list of dicts [{"audio": "beat1.wav", "genre": "reggaeton"}, ...]
    used_images = {}
    for info in beats_info:
        genre = info["genre"]
        audio_file = info["audio"]
        images = get_images_for_genre(images_base_folder, genre)
        if not images:
            raise Exception(f"No hay imágenes cargadas para el género {genre}. Por favor, agrega imágenes.")
        if genre not in used_images:
            used_images[genre] = set()
        available_images = [img for img in images if img not in used_images[genre]]
        if not available_images:
            raise Exception(f"No hay suficientes imágenes para el género {genre}.")
        image = random.choice(available_images)
        used_images[genre].add(image)
        audio_path = os.path.join(beats_folder, audio_file)
        output_name = f"{os.path.splitext(audio_file)[0]}_{genre}.mp4"
        genre_folder = os.path.join(output_folder, genre)
        os.makedirs(genre_folder, exist_ok=True)
        output_path = os.path.join(genre_folder, output_name)
        generate_video(audio_path, image, output_path)
        print(f"Generado: {output_path}")

# Ejemplo de uso (beats_info debe venir de la interfaz gráfica)
# beats_info = [{"audio": "beat1.wav", "genre": "reggaeton"}, {"audio": "beat2.wav", "genre": "guitarra"}, ...]
```

---

## Archivo de Referencia

Este archivo (`PROJECT_PLAN.md`) debe consultarse siempre antes de modificar el código.  
Define la lógica y las reglas del proyecto para evitar confusiones y errores.

---

## Notas Finales

- El sistema debe ser flexible para agregar nuevos géneros y nuevas imágenes.
- Siempre debe haber verificación de cantidad de imágenes suficientes para el lote.
- Si la IA necesita aclarar dudas, debe leer este archivo primero.