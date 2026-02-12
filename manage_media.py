"""
Script para crear las carpetas de media files si no existen
Ejecutar: python manage_media.py
"""
import os
from pathlib import Path

# Obtener el directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent
MEDIA_ROOT = BASE_DIR / 'media'

# Estructura de carpetas a crear
FOLDERS = [
    'companies/logos',
    'users/photos',
    'clients/documents',
]

def create_media_folders():
    """Crea las carpetas de media si no existen"""
    print("Creando estructura de carpetas para archivos multimedia...")
    
    # Crear carpeta media principal
    MEDIA_ROOT.mkdir(exist_ok=True)
    print(f"[OK] Carpeta creada: {MEDIA_ROOT}")
    
    # Crear subcarpetas
    for folder in FOLDERS:
        folder_path = MEDIA_ROOT / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        print(f"[OK] Carpeta creada: {folder_path}")
        
        # Crear archivo .gitkeep para mantener las carpetas en git
        gitkeep_file = folder_path / '.gitkeep'
        if not gitkeep_file.exists():
            gitkeep_file.touch()
            print(f"    [OK] Archivo .gitkeep creado")
    
    print("\n[SUCCESS] Estructura de carpetas creada exitosamente!")
    print(f"\nMedia Root: {MEDIA_ROOT}")
    print("\nEstructura:")
    print("media/")
    print("  - companies/logos/")
    print("  - users/photos/")
    print("  - clients/documents/")

if __name__ == '__main__':
    create_media_folders()
