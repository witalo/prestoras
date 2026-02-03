# PRESTORAS - Sistema de Gestión de Préstamos Multiempresa

Sistema multiempresa para la gestión de préstamos, cobranzas y clientes, diseñado para reflejar la realidad del negocio crediticio en Perú.

## 🚀 Características Principales

- **Sistema Multiempresa**: Cada empresa es independiente en datos y configuración
- **Gestión de Clientes**: Registro completo con documentos, clasificación automática y geolocalización
- **Préstamos Flexibles**: Tipos de préstamo configurables por empresa (Diario, Semanal, Mensual)
- **Sistema de Cuotas**: Generación automática de cuotas con capital e intereses
- **Mora Configurable**: Tipos de mora fija o porcentual, con ajustes registrados
- **Refinanciamientos**: Soporte completo para refinanciar préstamos con historial trazable
- **Rutas de Cobranza**: Zonas para organizar clientes y asignar cobradores
- **Autenticación Dual**: Login de empresa y login de usuario con tokens JWT (24 horas)
- **GraphQL API**: Backend con Django + Strawberry GraphQL
- **PostgreSQL**: Base de datos PostgreSQL con soporte para PostGIS

## 📋 Requisitos

- Python 3.10+
- PostgreSQL 12+
- Redis (opcional, para Celery)

## 🔧 Instalación

1. **Clonar el repositorio o navegar al directorio del proyecto**

2. **Crear y activar entorno virtual**:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate  # Windows
```

3. **Instalar dependencias**:
```bash
pip install -r requirements.txt
```

4. **Configurar base de datos PostgreSQL**:
   - Crear base de datos: `CREATE DATABASE prestoras;`
   - Configurar variables de entorno o editar `settings.py`

5. **Ejecutar migraciones**:
```bash
python manage.py makemigrations
python manage.py migrate
```

6. **Crear superusuario**:
```bash
python manage.py createsuperuser
```

7. **Iniciar servidor**:
```bash
python manage.py runserver
```

## 🔐 Autenticación

### Login de Empresa
```graphql
mutation {
  companyLogin(ruc: "12345678901", email: "empresa@example.com", password: "password") {
    success
    message
    token
    company {
      id
      ruc
      commercialName
    }
    expiresAt
  }
}
```

### Login de Usuario
```graphql
mutation {
  userLogin(dni: "12345678", password: "password", companyId: 1) {
    success
    message
    token
    user {
      id
      dni
      fullName
      role
    }
    expiresAt
  }
}
```

## 📱 Estructura del Proyecto

```
prestoras/
├── apps/
│   ├── companies/      # Gestión de empresas y tipos de préstamo
│   ├── users/          # Usuarios (Administradores y Cobradores)
│   ├── zones/          # Zonas de cobranza
│   ├── clients/        # Clientes y documentos
│   ├── loans/          # Préstamos, cuotas y refinanciamientos
│   └── payments/       # Pagos y ajustes de mora
├── prestoras/          # Configuración del proyecto
│   ├── settings.py     # Configuración Django
│   ├── schema.py       # Schema GraphQL principal
│   └── urls.py         # URLs del proyecto
└── requirements.txt    # Dependencias
```

## 📊 Modelos Principales

### Company (Empresa)
- RUC, Razón Social, Nombre Comercial
- Dirección fiscal y ubicación GPS
- Login de empresa (RUC, correo, contraseña)

### User (Usuario)
- DNI (usado como username para login)
- Teléfono, correo, foto
- Cargo: Administrador o Cobrador
- Zonas asignadas (para cobradores)

### Client (Cliente)
- DNI, nombres, apellidos
- Direcciones (domicilio y negocio)
- Geolocalización GPS
- Clasificación automática (Puntual, Regular, Moroso, Muy Moroso)

### Loan (Préstamo)
- Monto inicial, tasa de interés, número de cuotas
- Periodicidad (Diario, Semanal, Mensual)
- Generación automática de cuotas
- Configuración de mora
- Soporte para refinanciamiento

### Payment (Pago)
- Registro de pagos por cliente
- Métodos de pago: Efectivo, Tarjeta, BCP, Yape, Plin, Transferencia
- Asociación con cuotas específicas

## 🔄 Endpoint GraphQL

El endpoint GraphQL está disponible en:
```
http://localhost:8000/graphql/
```

## 📝 Notas Importantes

- Los tokens JWT expiran en 24 horas
- La mora solo se aplica si se supera la fecha final del crédito
- Un cliente puede tener múltiples préstamos activos simultáneamente
- El sistema actualiza automáticamente la clasificación de clientes según su historial
- Todos los ajustes de mora quedan registrados para auditoría

## 🛠️ Próximos Pasos

1. Instalar dependencias del proyecto
2. Configurar base de datos PostgreSQL
3. Ejecutar migraciones
4. Crear una empresa de prueba desde el admin de Django
5. Crear usuarios y clientes
6. Probar las queries y mutations GraphQL

## 📧 Soporte

Para preguntas o soporte, contactar al equipo de desarrollo.
