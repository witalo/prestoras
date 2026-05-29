"""
Mutations GraphQL para Companies usando Strawberry
Incluye login de empresa y CRUD de tipos de préstamo
"""
import strawberry
from typing import Optional
from datetime import datetime, timedelta
import jwt
from django.conf import settings

from .models import Company, LoanType
from .types import CompanyType, LoanTypeType


@strawberry.type
class CompanyLoginResult:
    """
    Resultado del login de empresa
    
    Retorna el token de empresa y la información de la empresa.
    """
    success: bool
    message: str
    token: Optional[str] = None
    company: Optional[CompanyType] = None
    expires_at: Optional[datetime] = None


def generate_jwt_token(payload: dict, expires_in_hours: int = 24) -> tuple[str, datetime]:
    """
    Genera un token JWT con expiración
    
    Args:
        payload: Datos a incluir en el token
        expires_in_hours: Horas de expiración (por defecto 24 horas)
    
    Returns:
        Tupla con (token, expires_at)
    """
    expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
    payload['exp'] = expires_at
    payload['iat'] = datetime.utcnow()
    
    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return token, expires_at


@strawberry.mutation
def company_login(
    ruc: str,
    email: str,
    password: str
) -> CompanyLoginResult:
    """
    Mutation para login de empresa
    
    El login de empresa requiere:
    - RUC de la empresa
    - Correo de la empresa
    - Contraseña de la empresa
    
    Retorna un token JWT válido por 24 horas.
    """
    try:
        # Buscar empresa por RUC o email
        try:
            # Intentar buscar por RUC primero
            company = Company.objects.filter(ruc=ruc).first()
            
            # Si no se encuentra por RUC, buscar por email
            if not company:
                company = Company.objects.filter(email=email).first()
            
            if not company:
                raise Company.DoesNotExist
        except Company.DoesNotExist:
            return CompanyLoginResult(
                success=False,
                message="Empresa no encontrada. Verifique el RUC o correo.",
                token=None,
                company=None,
                expires_at=None
            )
        
        # Verificar si la empresa está activa
        if not company.is_active:
            return CompanyLoginResult(
                success=False,
                message="La empresa está inactiva. Contacte al administrador.",
                token=None,
                company=None,
                expires_at=None
            )
        
        # Verificar contraseña
        if not company.check_password(password):
            return CompanyLoginResult(
                success=False,
                message="Contraseña incorrecta.",
                token=None,
                company=None,
                expires_at=None
            )
        
        # Generar token JWT (válido por 24 horas)
        payload = {
            'type': 'company',
            'company_id': company.id,
            'ruc': company.ruc,
        }
        
        token, expires_at = generate_jwt_token(payload, expires_in_hours=24)
        
        return CompanyLoginResult(
            success=True,
            message="Login exitoso",
            token=token,
            company=company,
            expires_at=expires_at
        )
    
    except Exception as e:
        return CompanyLoginResult(
            success=False,
            message=f"Error en el login: {str(e)}",
            token=None,
            company=None,
            expires_at=None
        )


@strawberry.type
class LoanTypeResult:
    success: bool
    message: str
    loan_type: Optional[LoanTypeType] = None


@strawberry.mutation
def create_loan_type(
    company_id: int,
    name: str,
    periodicity: str,
    interest_rate: float,
    suggested_installments: int,
    description: Optional[str] = None,
) -> LoanTypeResult:
    try:
        company = Company.objects.get(id=company_id)
        if LoanType.objects.filter(company=company, name=name).exists():
            return LoanTypeResult(success=False, message="Ya existe un tipo de préstamo con ese nombre.")
        loan_type = LoanType.objects.create(
            company=company,
            name=name,
            periodicity=periodicity,
            default_interest_rate=interest_rate,
            suggested_installments=suggested_installments,
            description=description,
            is_active=True,
        )
        return LoanTypeResult(success=True, message="Tipo de préstamo creado exitosamente.", loan_type=loan_type)
    except Company.DoesNotExist:
        return LoanTypeResult(success=False, message="Empresa no encontrada.")
    except Exception as e:
        return LoanTypeResult(success=False, message=f"Error: {str(e)}")


@strawberry.type
class DeleteLoanTypeResult:
    success: bool
    message: str


@strawberry.mutation
def delete_loan_type(loan_type_id: int) -> DeleteLoanTypeResult:
    try:
        loan_type = LoanType.objects.get(id=loan_type_id)
        # Solo eliminar si no tiene préstamos asociados
        from apps.loans.models import Loan
        if Loan.objects.filter(loan_type=loan_type).exists():
            return DeleteLoanTypeResult(
                success=False,
                message="No se puede eliminar: este tipo tiene préstamos registrados. Desactívalo en su lugar."
            )
        loan_type.delete()
        return DeleteLoanTypeResult(success=True, message="Tipo de préstamo eliminado.")
    except LoanType.DoesNotExist:
        return DeleteLoanTypeResult(success=False, message="Tipo de préstamo no encontrado.")
    except Exception as e:
        return DeleteLoanTypeResult(success=False, message=f"Error: {str(e)}")


@strawberry.mutation
def update_loan_type(
    loan_type_id: int,
    name: Optional[str] = None,
    periodicity: Optional[str] = None,
    interest_rate: Optional[float] = None,
    suggested_installments: Optional[int] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> LoanTypeResult:
    try:
        loan_type = LoanType.objects.get(id=loan_type_id)
        if name is not None:
            loan_type.name = name
        if periodicity is not None:
            loan_type.periodicity = periodicity
        if interest_rate is not None:
            loan_type.default_interest_rate = interest_rate
        if suggested_installments is not None:
            loan_type.suggested_installments = suggested_installments
        if description is not None:
            loan_type.description = description
        if is_active is not None:
            loan_type.is_active = is_active
        loan_type.save()
        return LoanTypeResult(success=True, message="Tipo de préstamo actualizado.", loan_type=loan_type)
    except LoanType.DoesNotExist:
        return LoanTypeResult(success=False, message="Tipo de préstamo no encontrado.")
    except Exception as e:
        return LoanTypeResult(success=False, message=f"Error: {str(e)}")
