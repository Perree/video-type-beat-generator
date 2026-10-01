# -*- coding: utf-8 -*-
"""
Constantes y configuración por defecto de la aplicación.
"""
import os

CONFIG_FILE = os.path.join('config', 'app_config.json')
# Extensiones de imagen (Pinterest y descargas: jfif, webp, etc.; FFmpeg las soporta)
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.jfif', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic')
IMAGE_EXTENSIONS_LIST = list(IMAGE_EXTENSIONS)
DEFAULT_CONFIG = {
    'last_output_folder': 'exported_videos',
    'last_channel': '',
    'last_group': '',
    'last_content_type': 'images',
    'last_beats_folder': '',
    'name_template': '[Type] {name} | Free for Profit',  # SEO: {name}, {channel}, {group}
    'overlay_enabled': False,
    'overlay_text': '{name} Type Beat',
    'cta_enabled': False,
    'cta_text': 'Like | Subscribe | Link in description',
    'channels': {}  # Canales: { "nombre": { "groups": [...] } }
}
