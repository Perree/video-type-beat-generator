#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thumbnail Generator - Sistema de Generación de Miniaturas
---------------------------------------------------------
Módulo para generar miniaturas automáticamente con diferentes templates y estilos.
Soporte para configuración personalizada por canal.
"""

import os
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple, Dict, List
import json

class ThumbnailTemplate:
    """Clase base para templates de miniaturas."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.width = 1280
        self.height = 720
    
    def generate(self, bg_image_path: str, output_path: str, **kwargs) -> bool:
        """Genera la miniatura usando este template."""
        raise NotImplementedError("Debe implementarse en la subclase")

class CenteredImageTemplate(ThumbnailTemplate):
    """Template de imagen centrada con bordes negros uniformes."""
    
    def __init__(self):
        super().__init__(
            "centered_image", 
            "Imagen centrada con bordes negros proporcionales"
        )
        
    def generate(self, bg_image_path: str, output_path: str, 
                border_ratio: float = 0.1, **kwargs) -> bool:
        """
        Genera miniatura con imagen centrada y bordes negros SOLAMENTE en los costados.
        La imagen ocupa toda la altura y se centra horizontalmente con bordes laterales.
        
        Args:
            bg_image_path: Ruta de la imagen de fondo
            output_path: Ruta donde guardar la miniatura
            border_ratio: Proporción del borde lateral (0.1 = 10% de cada costado)
        """
        try:
            # Cargar imagen original
            original_img = Image.open(bg_image_path).convert('RGB')
            
            # Crear canvas negro
            canvas = Image.new('RGB', (self.width, self.height), (0, 0, 0))
            
            # Calcular bordes SOLAMENTE laterales
            border_width = int(self.width * border_ratio)
            
            # Área útil para la imagen (sin bordes laterales, altura completa)
            useful_width = self.width - (2 * border_width)
            useful_height = self.height  # Altura completa, sin bordes arriba/abajo
            
            # Calcular escala manteniendo proporción
            scale_w = useful_width / original_img.width
            scale_h = useful_height / original_img.height
            scale = min(scale_w, scale_h)
            
            # Redimensionar imagen
            new_width = int(original_img.width * scale)
            new_height = int(original_img.height * scale)
            resized_img = original_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Centrar imagen horizontalmente, verticalmente centrada también
            x = (self.width - new_width) // 2
            y = (self.height - new_height) // 2
            
            canvas.paste(resized_img, (x, y))
            
            # Guardar miniatura
            canvas.save(output_path, 'JPEG', quality=95)
            return True
            
        except Exception as e:
            print(f"Error generando miniatura centrada: {e}")
            return False

class FullCoverTemplate(ThumbnailTemplate):
    """Template que usa la imagen completa como fondo."""
    
    def __init__(self):
        super().__init__(
            "full_cover", 
            "Imagen completa como fondo con recorte inteligente"
        )
    
    def generate(self, bg_image_path: str, output_path: str, 
                blur_background: bool = False, **kwargs) -> bool:
        """
        Genera miniatura usando toda la imagen como fondo.
        
        Args:
            bg_image_path: Ruta de la imagen de fondo
            output_path: Ruta donde guardar la miniatura
            blur_background: Si desenfoque el fondo
        """
        try:
            # Cargar imagen original
            original_img = Image.open(bg_image_path).convert('RGB')
            
            # Calcular recorte inteligente para 16:9
            orig_ratio = original_img.width / original_img.height
            target_ratio = self.width / self.height
            
            if orig_ratio > target_ratio:
                # Imagen más ancha, recortar los lados
                new_height = original_img.height
                new_width = int(new_height * target_ratio)
                left = (original_img.width - new_width) // 2
                cropped = original_img.crop((left, 0, left + new_width, new_height))
            else:
                # Imagen más alta, recortar arriba y abajo
                new_width = original_img.width
                new_height = int(new_width / target_ratio)
                top = (original_img.height - new_height) // 2
                cropped = original_img.crop((0, top, new_width, top + new_height))
            
            # Redimensionar a tamaño final
            final_img = cropped.resize((self.width, self.height), Image.Resampling.LANCZOS)
            
            # Aplicar desenfoque si se solicita
            if blur_background:
                from PIL import ImageFilter
                final_img = final_img.filter(ImageFilter.GaussianBlur(radius=2))
            
            # Guardar miniatura
            final_img.save(output_path, 'JPEG', quality=95)
            return True
            
        except Exception as e:
            print(f"Error generando miniatura full cover: {e}")
            return False

class ThumbnailGenerator:
    """Generador principal de miniaturas con múltiples templates."""
    
    def __init__(self):
        self.templates = {
            'centered_image': CenteredImageTemplate(),
            'full_cover': FullCoverTemplate()
        }
        
        # Configuraciones por canal
        self.channel_configs = {}
        self.config_file = os.path.join('config', 'thumbnail_config.json')
        self.load_channel_configs()
    
    def load_channel_configs(self):
        """Carga las configuraciones de miniaturas por canal."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.channel_configs = json.load(f)
            except Exception as e:
                print(f"Error cargando configuración de miniaturas: {e}")
                self.channel_configs = {}
    
    def generate_thumbnail(self, template_type, bg_image_path, output_path, **kwargs):
        """
        Genera una miniatura usando el template especificado.
        
        Args:
            template_type: Tipo de template ('centered_image', 'full_cover')
            bg_image_path: Ruta de la imagen de fondo
            output_path: Ruta donde guardar la miniatura
            **kwargs: Argumentos adicionales para el template
        """
        # Validar parámetros
        if not bg_image_path or not bg_image_path.strip():
            print("Error: bg_image_path está vacío")
            return False
            
        if not output_path or not output_path.strip():
            print("Error: output_path está vacío")
            return False
            
        if not os.path.exists(bg_image_path):
            print(f"Error: Archivo de imagen no encontrado: {bg_image_path}")
            return False
        
        if template_type not in self.templates:
            print(f"Error: Template '{template_type}' no encontrado")
            print(f"Templates disponibles: {list(self.templates.keys())}")
            return False
        
        template = self.templates[template_type]
        return template.generate(bg_image_path, output_path, **kwargs)
    
    def save_channel_configs(self):
        """Guarda las configuraciones de miniaturas por canal."""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.channel_configs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando configuración de miniaturas: {e}")
        """Guarda las configuraciones de miniaturas por canal."""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
    def save_channel_configs(self):
        """Guarda las configuraciones de miniaturas por canal."""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.channel_configs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando configuración de miniaturas: {e}")
    
    def set_channel_config(self, channel: str, template_name: str, **config):
        """Establece la configuración de miniatura para un canal."""
        self.channel_configs[channel] = {
            'template': template_name,
            'config': config
        }
        self.save_channel_configs()
    
    def get_channel_config(self, channel: str) -> Dict:
        """Obtiene la configuración de miniatura para un canal."""
        return self.channel_configs.get(channel, {
            'template': 'centered_image',
            'config': {}
        })
    
    def generate_thumbnail(self, bg_image_path: str, output_path: str, 
                          channel: str = None, template_override: str = None,
                          **kwargs) -> bool:
        """
        Genera una miniatura usando la configuración del canal o template especificado.
        
        Args:
            bg_image_path: Ruta de la imagen de fondo
            output_path: Ruta donde guardar la miniatura
            channel: Canal para usar su configuración (opcional)
            template_override: Template específico a usar (opcional)
            **kwargs: Parámetros adicionales para el template
        """
        # Determinar template y configuración
        if template_override and template_override in self.templates:
            template_name = template_override
            config = kwargs
        elif channel:
            channel_config = self.get_channel_config(channel)
            template_name = channel_config['template']
            config = {**channel_config['config'], **kwargs}
        else:
            template_name = 'centered_image'
            config = kwargs
        
        # Verificar que el template existe
        if template_name not in self.templates:
            print(f"Template '{template_name}' no encontrado")
            return False
        
        # Crear directorio de salida si no existe (solo si hay un directorio)
        output_dir = os.path.dirname(output_path)
        if output_dir:  # Solo crear directorios si hay una ruta
            os.makedirs(output_dir, exist_ok=True)
        
        # Generar miniatura
        template = self.templates[template_name]
        return template.generate(bg_image_path, output_path, **config)
    
    def get_available_templates(self) -> Dict[str, str]:
        """Retorna los templates disponibles con sus descripciones."""
        return {name: template.description for name, template in self.templates.items()}

# Función auxiliar para uso directo
def generate_thumbnail(bg_image_path: str, output_path: str, 
                      template: str = 'centered_image', **kwargs) -> bool:
    """
    Función de conveniencia para generar miniaturas directamente.
    
    Args:
        bg_image_path: Ruta de la imagen de fondo
        output_path: Ruta donde guardar la miniatura
        template: Template a usar ('centered_image', 'full_cover')
        **kwargs: Parámetros específicos del template
    """
    generator = ThumbnailGenerator()
    return generator.generate_thumbnail(bg_image_path, output_path, 
                                      template_override=template, **kwargs)
