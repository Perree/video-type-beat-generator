# Configurar la subida a YouTube (una sola vez)

> **2026-10-18:** el `client_secret.json` se importa al llavero desde Conexiones y el token del canal va directo a GitHub Secrets (no a `tokens/<canal>.json`). Ver [CLOUD_CREDENTIALS.md](CLOUD_CREDENTIALS.md).

1. Entrá a https://console.cloud.google.com/ y creá un proyecto (ej. "Type Beat Uploader").
2. **APIs y servicios → Biblioteca** → buscá **YouTube Data API v3** → **Habilitar**.
3. **Pantalla de consentimiento OAuth** (Google Auth Platform): tipo **Externo**, completá nombre y mail.
   Agregá los permisos `youtube.upload` y `youtube.readonly`.
4. En **Público / Usuarios de prueba** agregá el mail de **cada cuenta de Google** dueña de un canal.
5. Pasá la app a **"En producción"** (si queda en "Prueba", los tokens vencen cada 7 días y hay que reconectar).
   Google mostrará "app no verificada" al conectar: tocá *Configuración avanzada → Ir a la app*.
6. **Credenciales → Crear credenciales → ID de cliente OAuth → App de escritorio**. Descargá el JSON y
   guardalo como `config/client_secret.json` (no se sube al repo).
7. Instalá dependencias: `pip install -r requirements.txt`.

## Conectar cada canal
Gestión de Canales → seleccioná el canal → **🔗 Conectar canal (YouTube)** → en el navegador elegí la cuenta
de ese canal (si la cuenta tiene varios canales/marcas, elegí el correcto). El token queda en
`tokens/<canal>.json` (no versionado). Para cambiar de cuenta, volvé a tocar el botón.

## Subir
Marcá **"Subir a YouTube al terminar (privado)"** antes de generar. Al terminar:
- se usa la plantilla de descripción del canal (Fase 2) con BPM/key/link de la biblioteca;
- se usa como miniatura la imagen `<video>_imagen.jpg` si existe (requiere cuenta verificada por teléfono);
- si el beat ya se subió a ese canal, la app avisa y deja omitirlo;
- cada subida queda registrada en la tabla `uploads` de `library.db` con su `youtube_id` y URL.

## Límites importantes
- **Privado obligatorio** hasta que Google audite la app: los videos subidos por proyectos sin auditar quedan
  bloqueados en privado. Publicalos a mano desde YouTube Studio. Cuando quieras publicar/programar
  directo, pedí la auditoría: https://support.google.com/youtube/contact/yt_api_form
- **Cuota**: 10.000 unidades/día por proyecto. `videos.insert` ≈ 1.600 unidades (≈ 6 videos/día en total
  entre todos los canales), `thumbnails.set` 50, `channels.list` 1. Revisá el valor vigente en
  https://developers.google.com/youtube/v3/determine_quota_cost (no se pudo verificar al implementar)
  y el consumo en Google Cloud → APIs → YouTube Data API v3 → Cuotas. Se puede pedir aumento gratis.
