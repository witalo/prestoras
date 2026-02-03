# 🖥️ Frontend Electron + React + TypeScript - Setup

## 🎯 Stack Tecnológico

```
┌─────────────────────────────────────────┐
│   ELECTRON (Aplicación Desktop)         │
│   ┌─────────────────────────────────┐   │
│   │  REACT + TYPESCRIPT             │   │
│   │  ├── Material UI  o  Tailwind   │   │
│   │  ├── Apollo Client (GraphQL)    │   │
│   │  └── React Router               │   │
│   └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
         ↕️ HTTP/GraphQL
┌─────────────────────────────────────────┐
│   DJANGO BACKEND (GraphQL)              │
│   http://localhost:8000/graphql/        │
└─────────────────────────────────────────┘
```

## 📦 Tecnologías

### ✅ Recomendado:

**Frontend:**
- **Electron** - Aplicación de escritorio
- **React** - Framework UI
- **TypeScript** - Tipado estático
- **Material UI (MUI)** - Componentes modernos y profesionales
  O
- **Tailwind CSS** - Utility-first CSS (más flexible, más código)

**GraphQL:**
- **Apollo Client** o **React Query + GraphQL** - Cliente GraphQL
- **Code Generator** - Genera tipos TypeScript desde tu schema GraphQL

**Estado:**
- **Zustand** o **Redux Toolkit** - Estado global
- **React Context** - Para auth/empresa actual

**Routing:**
- **React Router** - Navegación

---

## 🗂️ Estructura del Proyecto

```
prestoras/
├── backend/                    # Tu Django actual
│   └── (todo lo que tienes)
│
└── frontend/                   # Nueva carpeta
    ├── electron-app/           # Aplicación Electron
    │   ├── package.json
    │   ├── electron/
    │   │   ├── main.ts        # Proceso principal Electron
    │   │   └── preload.ts     # Bridge de seguridad
    │   └── build/             # Build de React
    │
    └── react-app/             # Aplicación React
        ├── package.json
        ├── tsconfig.json
        ├── src/
        │   ├── components/    # Componentes reutilizables
        │   ├── pages/         # Páginas (Login, Dashboard, etc)
        │   ├── graphql/       # Queries/Mutations GraphQL
        │   │   ├── queries/
        │   │   ├── mutations/
        │   │   └── generated/ # Tipos generados
        │   ├── store/         # Estado global (Zustand)
        │   ├── hooks/         # Custom hooks
        │   ├── utils/         # Utilidades
        │   ├── types/         # Tipos TypeScript
        │   ├── App.tsx
        │   └── main.tsx
        └── public/
```

---

## 🔐 Flujo de Autenticación

### 1. Login

```typescript
// frontend/react-app/src/pages/Login.tsx

const LOGIN_MUTATION = gql`
  mutation UserLogin($dni: String!, $password: String!) {
    userLogin(dni: $dni, password: $password) {
      success
      message
      token
      user {
        id
        dni
        fullName
        role
        company {
          id
          legalName
        }
      }
      expiresAt
    }
  }
`;

function LoginPage() {
  const [login, { loading }] = useMutation(LOGIN_MUTATION);
  const { setAuthToken, setUser } = useAuthStore();
  
  const handleLogin = async (dni: string, password: string) => {
    const { data } = await login({ variables: { dni, password } });
    
    if (data.userLogin.success) {
      // Guardar token en secure storage (Electron safeStorage)
      await setAuthToken(data.userLogin.token);
      await setUser(data.userLogin.user);
      
      // Redirigir a dashboard
      navigate('/dashboard');
    }
  };
  
  return <LoginForm onSubmit={handleLogin} />;
}
```

### 2. Almacenamiento Seguro del Token (Electron)

```typescript
// frontend/react-app/src/utils/storage.ts

import { ipcRenderer } from 'electron';

export const storage = {
  async setToken(token: string): Promise<void> {
    // Electron safeStorage (encriptado por OS)
    await ipcRenderer.invoke('store-token', token);
  },
  
  async getToken(): Promise<string | null> {
    return await ipcRenderer.invoke('get-token');
  },
  
  async clearToken(): Promise<void> {
    await ipcRenderer.invoke('clear-token');
  }
};
```

### 3. Apollo Client con Auth Header

```typescript
// frontend/react-app/src/lib/apollo.ts

import { ApolloClient, InMemoryCache, createHttpLink, from } from '@apollo/client';
import { setContext } from '@apollo/client/link/context';
import { storage } from '../utils/storage';

const httpLink = createHttpLink({
  uri: 'http://localhost:8000/graphql/', // Tu endpoint GraphQL
});

const authLink = setContext(async (_, { headers }) => {
  const token = await storage.getToken();
  
  return {
    headers: {
      ...headers,
      authorization: token ? `Bearer ${token}` : '',
    }
  };
});

export const apolloClient = new ApolloClient({
  link: from([authLink, httpLink]),
  cache: new InMemoryCache(),
});
```

---

## 🎨 Material UI vs Tailwind

### Material UI (Recomendado para admin panel)

**Ventajas:**
- ✅ Componentes pre-hechos (DataGrid, DatePicker, etc.)
- ✅ Menos código CSS
- ✅ Temas profesionales
- ✅ Documentación excelente

**Ejemplo:**
```tsx
import { Button, TextField, Box } from '@mui/material';

function LoginForm() {
  return (
    <Box>
      <TextField label="DNI" />
      <TextField label="Contraseña" type="password" />
      <Button variant="contained">Ingresar</Button>
    </Box>
  );
}
```

### Tailwind CSS

**Ventajas:**
- ✅ Más flexible y personalizable
- ✅ Menor bundle size (tree-shaking)
- ✅ Control total del diseño

**Desventajas:**
- ❌ Más código JSX
- ❌ Necesitas crear componentes desde cero

---

## 📋 Setup Inicial Recomendado

### Paso 1: Crear estructura del frontend

```bash
# En la raíz del proyecto prestoras
mkdir frontend
cd frontend

# Crear React app con TypeScript
npm create vite@latest react-app -- --template react-ts
cd react-app
npm install

# Instalar Material UI
npm install @mui/material @emotion/react @emotion/styled
npm install @mui/icons-material
npm install @mui/x-data-grid  # Para tablas

# Instalar Apollo Client
npm install @apollo/client graphql

# Instalar React Router
npm install react-router-dom

# Instalar Zustand (estado global)
npm install zustand

# Instalar Code Generator (opcional pero recomendado)
npm install -D @graphql-codegen/cli @graphql-codegen/typescript @graphql-codegen/typescript-operations
```

### Paso 2: Configurar Electron

```bash
cd ..
npm create electron-app@latest electron-app
cd electron-app

npm install electron-store  # Para guardar datos localmente
npm install electron-updater  # Para actualizaciones automáticas
```

---

## 🚀 Ventajas de Electron

1. ✅ **Aplicación nativa** - Se ve como app de escritorio
2. ✅ **Offline-first** - Puede funcionar sin conexión (con caché)
3. ✅ **Acceso al sistema** - Notificaciones, menú, etc.
4. ✅ **Una sola instalación** - .exe / .dmg / .AppImage
5. ✅ **Misma base de código** - React funciona igual que web

---

## 📝 Próximos Pasos

1. ✅ Crear estructura de carpetas `frontend/`
2. ✅ Setup React + TypeScript con Vite
3. ✅ Configurar Material UI
4. ✅ Setup Apollo Client para GraphQL
5. ✅ Crear sistema de autenticación con JWT
6. ✅ Setup Electron wrapper
7. ✅ Crear página de Login
8. ✅ Crear Dashboard con menú lateral

---

## 🤔 Preguntas para ti:

1. **¿Prefieres Material UI o Tailwind?** (Yo recomiendo Material UI para admin panels)
2. **¿Quieres que genere tipos TypeScript desde tu schema GraphQL?** (Recomendado)
3. **¿Empiezo creando la estructura base del frontend?**

Dime y empezamos 🚀
