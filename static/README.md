# 📁 Carpeta Static - Archivos Estáticos del Sitio Web

Esta carpeta contiene archivos estáticos que se usan en la **interfaz web** del sistema.

## 📂 Estructura Recomendada

```
static/
├── css/
│   └── (archivos CSS del admin o web)
├── js/
│   └── (archivos JavaScript del admin o web)
├── images/
│   ├── logos/          # Logos del sistema, iconos
│   ├── icons/          # Iconos generales
│   └── backgrounds/    # Imágenes de fondo
└── admin/
    └── (personalización del admin de Django)
```

## 🔧 Uso

- **Archivos estáticos**: CSS, JS, imágenes del sitio web
- **Acceso**: `http://localhost:8000/static/images/logo.png`
- **Producción**: Se recopilan con `python manage.py collectstatic` a `staticfiles/`

## ⚠️ Diferencia con Media

- **static/**: Archivos del sistema (imágenes, CSS, JS del sitio web)
- **media/**: Archivos subidos por usuarios (fotos de clientes, logos de empresas, documentos)
