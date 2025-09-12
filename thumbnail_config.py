"""
Sistema de configuraciones para el editor de thumbnails
Maneja el guardado y carga de configuraciones por canal
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

class ThumbnailConfig:
    """Maneja la configuración de thumbnails por canal"""
    
    def __init__(self, config_dir: str = "thumbnail_configs"):
        self.config_dir = config_dir
        self.ensure_config_dir()
        
    def ensure_config_dir(self):
        """Crea el directorio de configuraciones si no existe"""
        os.makedirs(self.config_dir, exist_ok=True)
        
    def get_config_path(self, channel_name: str) -> str:
        """Obtiene la ruta del archivo de configuración para un canal"""
        safe_name = "".join(c for c in channel_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        return os.path.join(self.config_dir, f"{safe_name}.json")
        
    def save_config(self, channel_name: str, config_data: Dict[str, Any]) -> bool:
        """
        Guarda la configuración de un canal
        
        Args:
            channel_name: Nombre del canal
            config_data: Datos de configuración incluyendo overlays y propiedades
            
        Returns:
            bool: True si se guardó exitosamente
        """
        try:
            config_path = self.get_config_path(channel_name)
            
            # Añadir metadatos
            full_config = {
                "channel_name": channel_name,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "version": "1.0",
                "config": config_data
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(full_config, f, indent=2, ensure_ascii=False)
                
            return True
            
        except Exception as e:
            print(f"Error guardando configuración para {channel_name}: {e}")
            return False
            
    def load_config(self, channel_name: str) -> Optional[Dict[str, Any]]:
        """
        Carga la configuración de un canal
        
        Args:
            channel_name: Nombre del canal
            
        Returns:
            Dict con la configuración o None si no existe
        """
        try:
            config_path = self.get_config_path(channel_name)
            
            if not os.path.exists(config_path):
                return None
                
            with open(config_path, 'r', encoding='utf-8') as f:
                full_config = json.load(f)
                
            # Actualizar timestamp de acceso
            full_config["last_accessed"] = datetime.now().isoformat()
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(full_config, f, indent=2, ensure_ascii=False)
                
            return full_config.get("config", {})
            
        except Exception as e:
            print(f"Error cargando configuración para {channel_name}: {e}")
            return None
            
    def list_channels(self) -> List[Dict[str, Any]]:
        """
        Lista todos los canales con configuraciones guardadas
        
        Returns:
            Lista de diccionarios con información de canales
        """
        channels = []
        
        try:
            for filename in os.listdir(self.config_dir):
                if filename.endswith('.json'):
                    config_path = os.path.join(self.config_dir, filename)
                    
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                            
                        channel_info = {
                            "name": config.get("channel_name", filename[:-5]),
                            "created_at": config.get("created_at"),
                            "updated_at": config.get("updated_at"),
                            "last_accessed": config.get("last_accessed"),
                            "file_path": config_path
                        }
                        channels.append(channel_info)
                        
                    except Exception as e:
                        print(f"Error leyendo configuración {filename}: {e}")
                        
        except Exception as e:
            print(f"Error listando canales: {e}")
            
        # Ordenar por fecha de actualización (más recientes primero)
        channels.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return channels
        
    def delete_config(self, channel_name: str) -> bool:
        """
        Elimina la configuración de un canal
        
        Args:
            channel_name: Nombre del canal
            
        Returns:
            bool: True si se eliminó exitosamente
        """
        try:
            config_path = self.get_config_path(channel_name)
            
            if os.path.exists(config_path):
                os.remove(config_path)
                return True
            return False
            
        except Exception as e:
            print(f"Error eliminando configuración para {channel_name}: {e}")
            return False
            
    def duplicate_config(self, source_channel: str, target_channel: str) -> bool:
        """
        Duplica la configuración de un canal a otro
        
        Args:
            source_channel: Canal fuente
            target_channel: Canal destino
            
        Returns:
            bool: True si se duplicó exitosamente
        """
        try:
            source_config = self.load_config(source_channel)
            if source_config is None:
                return False
                
            return self.save_config(target_channel, source_config)
            
        except Exception as e:
            print(f"Error duplicando configuración de {source_channel} a {target_channel}: {e}")
            return False

class OverlayConfigSerializer:
    """Utilidades para serializar/deserializar configuraciones de overlays"""
    
    @staticmethod
    def serialize_overlay(overlay_item) -> Dict[str, Any]:
        """
        Serializa un overlay item a diccionario
        
        Args:
            overlay_item: Instancia de OverlayItem
            
        Returns:
            Dict con la configuración del overlay
        """
        return {
            "overlay_path": overlay_item.overlay_path,
            "x": overlay_item.x(),
            "y": overlay_item.y(),
            "scale": overlay_item.scale(),
            "rotation": overlay_item.rotation(),
            "opacity": overlay_item.opacity(),
            "z_value": overlay_item.zValue(),
            "visible": overlay_item.isVisible()
        }
        
    @staticmethod
    def serialize_scene(scene) -> Dict[str, Any]:
        """
        Serializa toda la escena a diccionario
        
        Args:
            scene: QGraphicsScene con overlays
            
        Returns:
            Dict con toda la configuración de la escena
        """
        from thumbnail_editor import OverlayItem
        
        overlays = []
        for item in scene.items():
            if isinstance(item, OverlayItem):
                overlays.append(OverlayConfigSerializer.serialize_overlay(item))
                
        return {
            "overlays": overlays,
            "background_image": getattr(scene, 'background_image_path', None),
            "canvas_size": [1280, 720]  # YouTube standard
        }
        
    @staticmethod
    def deserialize_to_scene(config: Dict[str, Any], scene, overlay_library=None):
        """
        Restaura la configuración en una escena
        
        Args:
            config: Diccionario con la configuración
            scene: QGraphicsScene destino
            overlay_library: Referencia a la librería de overlays para refresh
        """
        from thumbnail_editor import OverlayItem
        from PyQt6.QtCore import QPointF
        
        # Limpiar overlays existentes
        for item in scene.items():
            if isinstance(item, OverlayItem):
                scene.removeItem(item)
                
        # Restaurar overlays
        overlays_config = config.get("overlays", [])
        for overlay_config in overlays_config:
            try:
                overlay_path = overlay_config.get("overlay_path")
                if not overlay_path or not os.path.exists(overlay_path):
                    continue
                    
                # Crear overlay item
                overlay_item = OverlayItem(overlay_path)
                
                # Restaurar propiedades
                overlay_item.setPos(
                    overlay_config.get("x", 0), 
                    overlay_config.get("y", 0)
                )
                overlay_item.setScale(overlay_config.get("scale", 1.0))
                overlay_item.setRotation(overlay_config.get("rotation", 0))
                overlay_item.setOpacity(overlay_config.get("opacity", 1.0))
                overlay_item.setZValue(overlay_config.get("z_value", 1))
                overlay_item.setVisible(overlay_config.get("visible", True))
                
                # Añadir a la escena
                scene.addItem(overlay_item)
                
            except Exception as e:
                print(f"Error restaurando overlay {overlay_config}: {e}")
                
        # Actualizar librería si se proporciona
        if overlay_library:
            overlay_library.refresh_library()

# Funciones de utilidad para fácil integración

def create_default_config() -> Dict[str, Any]:
    """Crea una configuración por defecto"""
    return {
        "overlays": [],
        "background_image": None,
        "canvas_size": [1280, 720],
        "safe_zones": {
            "enabled": True,
            "mobile_safe_zone": True,
            "tv_safe_zone": True
        },
        "grid": {
            "enabled": False,
            "size": 20,
            "snap": False
        },
        "export": {
            "format": "PNG",
            "quality": 95,
            "background_color": [0, 0, 0, 255]
        }
    }

def get_recent_channels(limit: int = 10) -> List[Dict[str, Any]]:
    """Obtiene los canales usados recientemente"""
    config_manager = ThumbnailConfig()
    channels = config_manager.list_channels()
    return channels[:limit]

def quick_save(channel_name: str, scene) -> bool:
    """Función rápida para guardar la configuración actual"""
    try:
        config_manager = ThumbnailConfig()
        scene_config = OverlayConfigSerializer.serialize_scene(scene)
        return config_manager.save_config(channel_name, scene_config)
    except Exception as e:
        print(f"Error en guardado rápido: {e}")
        return False

def quick_load(channel_name: str, scene, overlay_library=None) -> bool:
    """Función rápida para cargar una configuración"""
    try:
        config_manager = ThumbnailConfig()
        config = config_manager.load_config(channel_name)
        if config:
            OverlayConfigSerializer.deserialize_to_scene(config, scene, overlay_library)
            return True
        return False
    except Exception as e:
        print(f"Error en carga rápida: {e}")
        return False