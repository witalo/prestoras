# 📁 Estructura de Archivos y Carpetas - PRESTORAS

## 📂 Estructura de Media Files

El sistema organiza los archivos multimedia en la siguiente estructura:

```
media/
├── companies/
│   └── logos/
│       └── {company_id}/
│           └── logo.{jpg|png|gif}
│
├── users/
│   └── photos/
│       └── {user_id}/
│           └── photo.{jpg|png|gif}
│
└── clients/
    └── documents/
        └── {client_id}/
            ├── dni.{jpg|png}
            ├── recibo_agua.{jpg|png}
            ├── recibo_luz.{jpg|png}
            └── otros/
                └── {archivo_additional}.{jpg|png|pdf}
```

## 🔧 Configuración

### URLs para Archivos Media

En **desarrollo** (DEBUG=True), los archivos se sirven automáticamente en:
- `http://localhost:8000/media/companies/logos/...`
- `http://localhost:8000/media/users/photos/...`
- `http://localhost:8000/media/clients/documents/...`

### En Producción

Para producción, configura tu servidor web (Nginx/Apache) para servir los archivos desde `MEDIA_ROOT`:
- **MEDIA_ROOT**: `D:\DJANGO\prestoras\media\` (o la ruta absoluta)
- **MEDIA_URL**: `/media/`

## 📸 Campos Base64 en GraphQL

El sistema expone campos base64 para facilitar el envío de imágenes al frontend:

### CompanyType
- `logo_url`: URL directa del logo
- `logo_base64`: Logo en formato base64 (para login de empresa)

### UserType
- `photo_url`: URL directa de la foto
- `photo_base64`: Foto en formato base64

### ClientDocumentType
- `file_url`: URL directa del documento
- `file_base64`: Documento en formato base64 (para DNI, recibos, etc.)

## 📋 Formato Base64

Los campos base64 retornan strings en formato **Data URL**:
```
data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD...
```

Esto permite:
1. Mostrar las imágenes directamente en `<img src="...">`
2. Enviar las imágenes en el login sin necesidad de hacer requests adicionales
3. Guardar las imágenes en el frontend (Room/DataStore) para uso offline

## 💡 Ejemplo de Uso

### Query GraphQL - Obtener logo de empresa en base64

```graphql
query {
  companyLogin(ruc: "12345678901", email: "empresa@example.com", password: "password") {
    success
    token
    company {
      id
      commercialName
      logoUrl      # URL directa
      logoBase64   # Base64 para guardar en Room/DataStore
    }
  }
}
```

### Query GraphQL - Obtener documentos de cliente

```graphql
query {
  client(clientId: 1) {
    id
    fullName
    documents {
      id
      documentType
      fileUrl       # URL directa
      fileBase64    # Base64 para mostrar en la app
    }
  }
}
```

## 🗂️ Organización por Tipo de Documento

Los documentos de clientes se organizan así:
- **DNI**: Foto frontal y/o reverso del DNI
- **RECEIPT**: Recibos de servicios (agua, luz)
- **CONTRACT**: Contratos firmados
- **ADDITIONAL**: Fotos adicionales del cliente o negocio
- **OTHER**: Otros documentos

## ⚠️ Notas Importantes

1. **Tamaño de archivos**: Los archivos grandes pueden generar strings base64 muy largos. Considera comprimir las imágenes antes de subirlas.

2. **Permisos**: Asegúrate de que la carpeta `media/` tenga permisos de escritura.

3. **Backup**: Incluye la carpeta `media/` en tus backups, ya que contiene información crítica (DNIs, recibos, etc.).

4. **Seguridad**: En producción, considera restringir el acceso a ciertos documentos según el rol del usuario.
