# 📋 Ejemplo: Tipos de Préstamo por Empresa

## ✅ CORRECTO: Una empresa puede tener MÚLTIPLES tipos de préstamo

### Empresa: "Créditos Rápido S.A.C."

La empresa puede configurar **TODOS** estos tipos de préstamo:

```
Tipo 1: "Préstamo Diario"
  - Periodicidad: Diario
  - Tasa de interés: 2% diario
  - Cuotas sugeridas: 30 días
  - Clientes: Trabajadores informales (vendedores ambulantes)

Tipo 2: "Préstamo Semanal"  
  - Periodicidad: Semanal
  - Tasa de interés: 8% semanal
  - Cuotas sugeridas: 4 semanas
  - Clientes: Emprendedores pequeños

Tipo 3: "Préstamo Mensual"
  - Periodicidad: Mensual
  - Tasa de interés: 15% mensual
  - Cuotas sugeridas: 6 meses
  - Clientes: Negocios establecidos
```

## 🔄 Cómo funciona en la práctica:

### Escenario 1: Cliente necesita dinero rápido
- **Cliente**: Juan (vendedor ambulante)
- **Solicita**: S/ 500 para comprar mercadería
- **Empresa ofrece**: "Préstamo Diario" (paga todos los días)
- **Resultado**: Préstamo creado usando el Tipo 1

### Escenario 2: Cliente necesita plazo más largo
- **Cliente**: María (tiene tienda)
- **Solicita**: S/ 5,000 para ampliar negocio
- **Empresa ofrece**: "Préstamo Mensual" (paga mensualmente)
- **Resultado**: Préstamo creado usando el Tipo 3

### Escenario 3: Cliente intermedio
- **Cliente**: Carlos (microempresario)
- **Solicita**: S/ 2,000 para emergencia
- **Empresa ofrece**: "Préstamo Semanal" (paga semanalmente)
- **Resultado**: Préstamo creado usando el Tipo 2

## 📊 Estructura en la Base de Datos:

```
Company: "Créditos Rápido S.A.C."
├── LoanType 1: "Préstamo Diario"    ← Existe simultáneamente
├── LoanType 2: "Préstamo Semanal"   ← Existe simultáneamente
└── LoanType 3: "Préstamo Mensual"   ← Existe simultáneamente

Cuando se crea un préstamo:
├── Loan #1 → usa LoanType 1 (Diario)
├── Loan #2 → usa LoanType 2 (Semanal)
├── Loan #3 → usa LoanType 3 (Mensual)
└── Loan #4 → usa LoanType 1 (Diario) nuevamente
```

## 💡 Ventajas de tener múltiples tipos:

1. **Flexibilidad**: Ofreces diferentes opciones según el cliente
2. **Segmentación**: Cada tipo atiende un perfil diferente
3. **Competitividad**: Puedes competir en diferentes segmentos
4. **Gestión**: Fácil administrar diferentes políticas de crédito

## ❌ Lo que NO significa:

- ❌ NO significa que una empresa solo puede tener UN tipo
- ❌ NO significa que debes limitar a 3 tipos
- ❌ NO significa que cada cliente solo puede tener un tipo

## ✅ Lo que SÍ significa:

- ✅ Una empresa puede tener **todos los tipos que quiera**
- ✅ Puedes crear más tipos según necesidades (Quincenal, Trimestral, etc.)
- ✅ Cada préstamo individual usa **uno** de esos tipos como plantilla
- ✅ Pero la empresa mantiene **todos** sus tipos disponibles
