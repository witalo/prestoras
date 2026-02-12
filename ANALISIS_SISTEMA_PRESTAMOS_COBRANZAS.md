# Análisis: Sistema de Préstamos y Cobranzas Multiempresa

## Resumen ejecutivo

Tu backend y app ya cubren el **núcleo del negocio**: empresas, usuarios (admin/cobrador), clientes, zonas, tipos de préstamo, préstamos con cuotas, pagos, mora, refinanciamiento y ajustes de mora. Para tener un **sistema completo y con buen control**, faltan sobre todo:

1. **Gestión completa de Zonas y Tipos de Préstamo** (backend + app).
2. **Gestión de usuarios** (crear/editar cobradores y asignar zonas).
3. **Reportes y estadísticas** por empresa (dashboard, cobranza, morosidad, cartera).
4. **Algunos filtros y consultas** en backend (préstamos por zona, por rango de fechas).
5. **Pantallas en la app**: Zonas (CRUD), Estadísticas/Reportes, y uso de zona en clientes.

Todo lo que se liste debe estar **filtrado por empresa** (multiempresa).

---

## 1. Lo que YA tienes (resumen)

| Módulo | Backend | App Android |
|--------|---------|-------------|
| **Empresa** | Login, queries (company, companies, loan_types_by_company) | Login empresa, datos en sesión |
| **Usuario** | Login usuario (DNI + password) | Login usuario |
| **Clientes** | CRUD, búsqueda, por zona, por cobrador, documentos | Lista, crear/editar, préstamos del cliente |
| **Zonas** | create_zone, update_zone, zones, zone | Solo placeholder "próximamente" |
| **Tipos de préstamo** | Solo lectura (loan_types_by_company) | Se usan al crear préstamo |
| **Préstamos** | create, update, delete, refinance, update_penalty; queries (loans, loan, active_loans_by_client, overdue_loans, client_loan_history, installments) | Lista, filtro por fecha, crear, detalle, pagar, voucher, compartir PDF |
| **Pagos** | create, update; loan_payments, collector_payments, payment, paymentVoucher | Registrar pago desde detalle de préstamo, voucher e impresión |

Modelos: Company, User (con zones M2M), Zone, LoanType, Client, ClientDocument, Loan, Installment, Refinancing, Payment, PaymentInstallment, PenaltyAdjustment. Todo correcto para multiempresa.

---

## 2. Lo que FALTA para un sistema completo

### 2.1 Backend (Django/GraphQL)

#### A) Empresas y configuración

- **CRUD Empresa** (opcional si solo se crean por admin):  
  - createCompany, updateCompany (datos fiscales, logo, dirección, etc.).  
  - Si las empresas solo se dan de alta desde Django Admin, se puede dejar como está.
- **CRUD Tipos de préstamo** (sí necesario para que la app sea autosuficiente):
  - **createLoanType**: company_id, name, periodicity, default_interest_rate, suggested_installments, description.
  - **updateLoanType**: id, mismos campos opcionales.
  - **deleteLoanType** o desactivar: is_active = false (evitar borrar si hay préstamos que lo referencian).

#### B) Zonas

- **create_zone / update_zone**: ya existen.
- Opcional: **delete_zone** o “baja lógica” (poner status = INACTIVE y no permitir asignar nuevos clientes/cobradores).
- Opcional: campos latitude/longitude en create/update si quieres usarlos en la app.

#### C) Usuarios (cobradores y administradores)

- **createUser**: company_id, dni, email, first_name, last_name, password, role (ADMIN/COLLECTOR), phone (opcional).
- **updateUser**: id, campos opcionales (nombre, email, teléfono, role, is_active).
- **assignCollectorZones**: user_id, zone_ids (lista). Actualizar el M2M User–Zone para que el cobrador tenga asignadas solo esas zonas.
- **users** / **usersByCompany**: lista de usuarios de la empresa (para admin y para asignar cobradores a zonas).

Sin esto, no puedes dar de alta cobradores ni asignarles zonas desde la app (solo desde Django Admin).

#### D) Préstamos y consultas

- **Filtro por zona** en préstamos:  
  - En `loans` (o en una query dedicada), aceptar `zone_id` opcional: préstamos de clientes que pertenecen a esa zona.  
  - Muy útil para reportes “por zona” y para que el cobrador vea solo su zona si se filtra por zona del usuario.
- **Filtro por rango de fechas de creación**:  
  - `start_date`, `end_date` (por `created_at` o por `start_date` del préstamo) para “préstamos del día” o “préstamos de la semana”.  
  - Ya tienes lógica en la app para “préstamos del día”; asegurar que el backend permita filtrar por fecha sin depender solo de traer “todo” y filtrar en cliente.

#### E) Reportes y estadísticas (nuevo módulo o queries)

Todo por **company_id** (multiempresa). Sugerencia: una app `reports` o extender queries en `payments` y `loans`.

1. **Dashboard / Resumen por empresa**
   - Cartera activa: suma de `pending_amount` de préstamos con status ACTIVE/DEFAULTING.
   - Total desembolsado: suma de `initial_amount` de préstamos activos (o todos si quieres).
   - Cobrado hoy / esta semana / este mes: suma de `Payment.amount` donde `payment_date` en ese rango y status COMPLETED.
   - Cantidad de préstamos por estado: ACTIVE, DEFAULTING, COMPLETED, REFINANCED, CANCELLED.
   - Número de clientes activos (con al menos un préstamo activo) y opcionalmente clientes morosos.

2. **Reporte de cobranza**
   - Por cobrador y rango de fechas: total cobrado, cantidad de pagos.
   - Por zona y rango de fechas: total cobrado, cantidad de pagos (pagos de préstamos cuyos clientes están en esa zona).
   - Detalle opcional: lista de pagos (payment_id, client, amount, date).

3. **Reporte de morosidad**
   - Préstamos vencidos (end_date &lt; hoy y status ACTIVE o DEFAULTING): por empresa, opcionalmente por zone_id.
   - Monto en mora: suma de pending_amount + penalty_applied de esos préstamos.
   - Lista de morosos: cliente, préstamo, días de atraso, monto pendiente, mora.

4. **Reporte de cartera**
   - Préstamos activos por tipo (loan_type): cantidad y monto total (initial_amount o pending_amount).
   - Por zona: cantidad de préstamos activos y monto pendiente por zona.
   - Total a recuperar: suma de pending_amount (+ penalty_applied si quieres) por empresa.

5. **Reporte de pagos del día / período**
   - Pagos registrados en un rango de fechas (por empresa, opcional por cobrador): total, cantidad, detalle (opcional).

6. **Reporte por cobrador**
   - Por usuario (cobrador) y período: total cobrado, cantidad de operaciones, lista de pagos (para evaluación y comisiones si aplica).

Implementación sugerida: **queries GraphQL** que devuelvan tipos “report” (por ejemplo `DashboardStats`, `CollectionReport`, `DelinquencyReport`, `PortfolioReport`) con los campos necesarios, siempre recibiendo `company_id` y, donde aplique, `start_date`, `end_date`, `zone_id`, `collector_id`.

---

### 2.2 App Android

#### A) Zonas

- **Lista de zonas** de la empresa (usar query `zones(companyId)`).
- **Crear zona**: pantalla/form con nombre, descripción (y opcional lat/long); llamar `createZone`.
- **Editar zona**: mismo formulario con `updateZone`; opcional “desactivar” (update con is_active = false).
- Navegación: reemplazar el `PlaceholderScreen` de Zonas por esta pantalla; rutas ya existen (ZONES, CREATE_ZONE).

#### B) Clientes y zona

- En el formulario de cliente (crear/editar): **selector de zona** (dropdown o lista) cargado desde `zones(companyId)`. Al guardar, enviar `zone_id` en createClient/updateClient (el backend ya lo soporta).

#### C) Tipos de préstamo (opcional pero recomendable)

- Si añades create/update LoanType en backend:
  - Pantalla “Tipos de préstamo”: lista (loan_types_by_company), crear y editar (nombre, periodicidad, tasa, cuotas sugeridas). Solo para rol ADMIN.

#### D) Reportes / Estadísticas

- Reemplazar el **PlaceholderScreen de Estadísticas** por una pantalla de reportes:
  - Selector de período (hoy, semana, mes) y opcionalmente zona o cobrador.
  - Llamar a las nuevas queries de reportes (dashboard, cobranza, morosidad, etc.).
  - Mostrar:
    - Resumen: cartera activa, cobrado en período, cantidad de préstamos por estado, morosidad.
    - Listas: morosos, pagos del día, cobranza por cobrador (si el usuario es admin).
  - Todo filtrado por la empresa de la sesión (multiempresa).

#### E) Usuarios y asignación de zonas (si hay backend)

- Si implementas createUser/updateUser/assignCollectorZones:
  - Pantalla “Usuarios” (solo ADMIN): lista de usuarios de la empresa, crear cobrador/admin, editar, asignar zonas al cobrador (checkboxes o multi-select de zonas).

#### F) Pagos (pantalla global)

- La ruta “Pagos” hoy es un placeholder. Opciones:
  - **Lista de pagos**: por rango de fechas (y opcional por cobrador), usando `collector_payments` o una query de “pagos por empresa y fechas”. Útil para ver “todos los pagos del día”.
  - O dejar que el flujo principal siga siendo: Préstamos → Detalle → Pagar; y usar “Pagos” solo para esta lista/consulta.

#### G) Perfil

- Pantalla Perfil: datos del usuario logueado (nombre, DNI, correo, rol, empresa). Opcional: cambiar contraseña si añades mutation en backend.

---

## 3. Reportes que deberías tener (checklist multiempresa)

Cada reporte debe poder filtrarse por **empresa** (company_id de la sesión). Donde aplique, por **zona**, **cobrador** y **rango de fechas**.

| # | Reporte | Descripción | Filtros típicos |
|---|---------|-------------|------------------|
| 1 | **Dashboard / Resumen ejecutivo** | Cartera activa, cobrado (día/semana/mes), préstamos por estado, clientes activos/morosos | company_id |
| 2 | **Cobranza por período** | Total cobrado y cantidad de pagos en un rango de fechas | company_id, start_date, end_date |
| 3 | **Cobranza por cobrador** | Total y cantidad de pagos por cobrador en un período | company_id, collector_id, start_date, end_date |
| 4 | **Cobranza por zona** | Total y cantidad de pagos por zona en un período | company_id, zone_id, start_date, end_date |
| 5 | **Morosidad** | Préstamos vencidos, monto en mora, lista de morosos (cliente, préstamo, días atraso, monto) | company_id, zone_id (opcional) |
| 6 | **Cartera por tipo de préstamo** | Préstamos activos por tipo (cantidad y montos) | company_id |
| 7 | **Cartera por zona** | Préstamos activos y monto pendiente por zona | company_id |
| 8 | **Pagos del día** | Lista de pagos del día (o de un rango) para cierre de caja | company_id, date (o start/end) |
| 9 | **Histórico de cobranza** | Serie temporal (por día o por semana) de lo cobrado para gráficos | company_id, start_date, end_date |

Los 1–5 y 8 son los más importantes para control operativo y gerencial. 6–7 y 9 mejoran análisis y trazabilidad.

---

## 4. Orden sugerido de implementación

1. **Backend**
   - CRUD Tipos de préstamo (createLoanType, updateLoanType, desactivar).
   - CRUD Usuarios y asignación de zonas (createUser, updateUser, assignCollectorZones, usersByCompany).
   - Queries de reportes: dashboard, cobranza (por período/cobrador/zona), morosidad, cartera (por tipo/zona), pagos del día.
   - Filtro por zona y por rango de fechas en préstamos (si no está ya).

2. **App Android**
   - Pantalla Zonas: lista, crear, editar (y opcional desactivar).
   - Selector de zona en formulario de cliente.
   - Pantalla Estadísticas/Reportes usando las nuevas queries (resumen + listas clave).
   - (Opcional) Pantalla Usuarios y asignación de zonas si el backend está listo.
   - (Opcional) Pantalla Tipos de préstamo si el backend está listo.
   - Pantalla Pagos: lista de pagos por fechas (y por cobrador si aplica).
   - Pantalla Perfil básica.

Con esto tendrás un sistema de préstamos y cobranzas **completo, multiempresa, con buen control y reportes útiles**. Si indicas por dónde quieres empezar (backend reportes, zonas en app, o usuarios), se puede bajar a tareas concretas por archivo y por query/mutation.
