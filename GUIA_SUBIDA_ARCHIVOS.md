# 📸 Guía de Subida de Archivos - PRESTORAS

## ✅ Configuración Completada

El sistema está **100% listo** para recibir, guardar y servir imágenes de documentos de clientes.

## 📁 Tipos de Documentos Soportados

```python
DOCUMENT_TYPE_CHOICES = [
    ('DNI', 'Foto de DNI'),
    ('RECEIPT', 'Recibo (Agua/Luz)'),
    ('ADDITIONAL', 'Foto Adicional'),
    ('CONTRACT', 'Contrato'),
    ('OTHER', 'Otro'),
]
```

## 🗂️ Estructura de Guardado

Los archivos se guardan automáticamente en:
```
media/clients/documents/
  └── {dni_cliente}_{tipo_documento}_{uuid}.{extension}
```

Ejemplos:
- `media/clients/documents/12345678_dni_a1b2c3d4.jpg`
- `media/clients/documents/12345678_receipt_e5f6g7h8.png`
- `media/clients/documents/12345678_additional_i9j0k1l2.pdf`

## 🔧 Mutations Disponibles

### 1. Crear Documento de Cliente

```graphql
mutation {
  createClientDocument(
    clientId: 1
    documentType: "DNI"
    fileBase64: "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    description: "DNI frontal del cliente"
  ) {
    success
    message
    document {
      id
      documentType
      fileUrl
      fileBase64
      description
      createdAt
    }
  }
}
```

**Parámetros:**
- `clientId` (requerido): ID del cliente
- `documentType` (requerido): "DNI", "RECEIPT", "ADDITIONAL", "CONTRACT", o "OTHER"
- `fileBase64` (requerido): Archivo en base64 (con o sin prefijo `data:image/...`)
- `description` (opcional): Descripción del documento

### 2. Actualizar Documento de Cliente

```graphql
mutation {
  updateClientDocument(
    documentId: 1
    documentType: "DNI"  # Opcional
    fileBase64: "data:image/jpeg;base64,..."  # Opcional
    description: "DNI actualizado"  # Opcional
  ) {
    success
    message
    document {
      id
      documentType
      fileUrl
      fileBase64
    }
  }
}
```

**Parámetros:**
- `documentId` (requerido): ID del documento a actualizar
- `documentType` (opcional): Nuevo tipo de documento
- `fileBase64` (opcional): 
  - Si se envía: Actualiza el archivo
  - Si es `""` (string vacío): Elimina el archivo actual
  - Si es `null`: No modifica el archivo
- `description` (opcional): Nueva descripción

## 📤 Formato Base64

### Desde Android (Kotlin/Java)

```kotlin
// Convertir imagen a base64
val bitmap = BitmapFactory.decodeFile(imagePath)
val outputStream = ByteArrayOutputStream()
bitmap.compress(Bitmap.CompressFormat.JPEG, 90, outputStream)
val imageBytes = outputStream.toByteArray()
val base64Image = Base64.encodeToString(imageBytes, Base64.NO_WRAP)

// O con prefijo data URL (recomendado)
val base64Image = "data:image/jpeg;base64,${Base64.encodeToString(imageBytes, Base64.NO_WRAP)}"
```

### Desde JavaScript/TypeScript

```javascript
// Leer archivo y convertir a base64
const file = event.target.files[0];
const reader = new FileReader();

reader.onloadend = () => {
  const base64 = reader.result; // Ya viene con "data:image/jpeg;base64,..."
  // Usar base64 en la mutation
};
reader.readAsDataURL(file);
```

## ✅ Características del Sistema

1. **✅ Guardado Automático**: Los archivos se guardan automáticamente en `media/clients/documents/`
2. **✅ Nombres Únicos**: Se generan nombres únicos con UUID para evitar conflictos
3. **✅ Múltiples Formatos**: Soporta JPG, PNG, GIF, WebP y PDF
4. **✅ Detección Automática**: Detecta el tipo de archivo desde el base64
5. **✅ URLs Accesibles**: Los archivos son accesibles en `/media/clients/documents/...`
6. **✅ Base64 de Retorno**: Puedes obtener el archivo en base64 con `fileBase64`
7. **✅ Actualización Segura**: Puedes actualizar o eliminar archivos sin problemas

## 📋 Ejemplo Completo

### Crear Cliente con Múltiples Documentos

```graphql
# 1. Crear documento DNI
mutation CreateDNI {
  createClientDocument(
    clientId: 1
    documentType: "DNI"
    fileBase64: "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    description: "DNI frontal"
  ) {
    success
    document { id fileUrl }
  }
}

# 2. Crear recibo de agua
mutation CreateReciboAgua {
  createClientDocument(
    clientId: 1
    documentType: "RECEIPT"
    fileBase64: "data:image/png;base64,iVBORw0KGgo..."
    description: "Recibo de agua - Enero 2026"
  ) {
    success
    document { id fileUrl }
  }
}

# 3. Crear foto adicional
mutation CreateFotoAdicional {
  createClientDocument(
    clientId: 1
    documentType: "ADDITIONAL"
    fileBase64: "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    description: "Foto del negocio del cliente"
  ) {
    success
    document { id fileUrl }
  }
}
```

## 🔍 Consultar Documentos de un Cliente

```graphql
query {
  client(clientId: 1) {
    id
    fullName
    documents {
      id
      documentType
      fileUrl
      fileBase64  # Para mostrar en la app
      description
      createdAt
    }
  }
}
```

## ⚠️ Notas Importantes

1. **Tamaño de Archivo**: Considera comprimir imágenes grandes antes de subirlas
2. **Base64 Completo**: Puedes enviar con prefijo `data:image/...;base64,` o solo el base64
3. **Manejo de Errores**: Las mutations retornan `success: false` si hay errores
4. **Eliminar Archivos**: Para eliminar, usa `updateClientDocument` con `fileBase64: ""`
5. **Múltiples Documentos**: Un cliente puede tener múltiples documentos del mismo tipo

## 🎉 ¡Todo Listo!

El sistema está **completamente configurado** y listo para:
- ✅ Recibir imágenes en base64
- ✅ Guardarlas en la estructura correcta
- ✅ Servirlas mediante URLs
- ✅ Retornarlas en base64 cuando se necesite
- ✅ Actualizar y eliminar documentos

¡Puedes empezar a usar las mutations ahora mismo! 🚀
