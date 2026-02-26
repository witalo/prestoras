"""
Modelo de Usuario extendido de Django
Incluye DNI, teléfono, correo y cargo del empleado
Tipos: Administrador, Cobrador
"""
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models

# Opciones para cargo/rol del usuario
USER_ROLE_CHOICES = [
    ('ADMIN', 'Administrador'),
    ('COLLECTOR', 'Cobrador'),
]


class UserManager(BaseUserManager):
    """
    Manager personalizado para el modelo User
    El username será el DNI
    """
    def create_user(self, dni, email, password=None, **extra_fields):
        """
        Crea y retorna un usuario regular con DNI y email
        """
        if not dni:
            raise ValueError('El DNI es obligatorio')
        if not email:
            raise ValueError('El email es obligatorio')
        
        email = self.normalize_email(email)
        # NO pasamos username porque el modelo usa dni como USERNAME_FIELD
        user = self.model(dni=dni, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, dni, email, password=None, **extra_fields):
        """
        Crea y retorna un superusuario
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'ADMIN')
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(dni, email, password, **extra_fields)


class User(AbstractUser):
    """
    Modelo de Usuario personalizado
    
    Extiende el modelo User de Django agregando:
    - DNI (usado como username)
    - Teléfono
    - Correo (ya existe en AbstractUser pero lo usamos explícitamente)
    - Cargo/Rol (Administrador o Cobrador)
    - Foto
    - Empresa asociada
    - Zonas asignadas (para cobradores)
    """
    # Username será el DNI
    username = None  # Deshabilitamos username estándar
    
    # DNI (identificador principal para login de usuario)
    dni = models.CharField(
        'DNI',
        max_length=8,
        unique=True,
        null=False,
        blank=False,
        help_text='DNI del usuario (8 dígitos) - usado para login'
    )
    
    # Email (obligatorio)
    email = models.EmailField(
        'Correo Electrónico',
        unique=True,
        null=False,
        blank=False
    )
    
    # Teléfono
    phone = models.CharField(
        'Teléfono/Celular',
        max_length=15,
        null=True,
        blank=True
    )
    
    # Cargo/Rol del empleado
    role = models.CharField(
        'Cargo',
        max_length=20,
        choices=USER_ROLE_CHOICES,
        default='COLLECTOR',
        help_text='Rol del usuario: Administrador o Cobrador'
    )
    
    # Foto del usuario
    photo = models.ImageField(
        'Foto',
        upload_to='users/photos/',
        blank=True,
        null=True
    )
    
    # Empresa a la que pertenece el usuario
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True,
        help_text='Empresa a la que pertenece este usuario'
    )
    
    # Cartera de clientes asignados (vía Client.collectors / ClientCollector).
    # Acceso: user.assigned_clients (queryset de Client).
    
    # Campos de Django que usamos
    first_name = models.CharField('Nombres', max_length=150, blank=True)
    last_name = models.CharField('Apellidos', max_length=150, blank=True)
    is_active = models.BooleanField('Activo', default=True)
    is_staff = models.BooleanField('Es Staff', default=False)
    is_superuser = models.BooleanField('Es Superusuario', default=False)
    date_joined = models.DateTimeField('Fecha de Registro', auto_now_add=True)
    
    # USERNAME_FIELD indica qué campo se usa para login
    USERNAME_FIELD = 'dni'
    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']
    
    objects = UserManager()
    
    @property
    def full_name(self):
        """Retorna el nombre completo del usuario"""
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def is_admin(self):
        """Retorna True si el usuario es administrador"""
        return self.role == 'ADMIN' or self.is_superuser
    
    @property
    def is_collector(self):
        """Retorna True si el usuario es cobrador"""
        return self.role == 'COLLECTOR'
    
    def __str__(self):
        return f"{self.dni} - {self.full_name or self.email}"
    
    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['first_name', 'last_name']
        indexes = [
            models.Index(fields=['dni']),
            models.Index(fields=['email']),
            models.Index(fields=['company', 'role']),
            models.Index(fields=['is_active']),
        ]
