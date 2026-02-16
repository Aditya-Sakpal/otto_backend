"""
Role-Based Access Control (RBAC) permissions.

Provides dependency injection for role-based authorization.
"""
from typing import List
from fastapi import Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.logging import get_logger
from app.domain.enums import UserRole
from app.domain.users.models import User

logger = get_logger(__name__)


# RBAC DISABLED - All APIs are now open
# def require_roles(allowed_roles: List[UserRole]):
#     """
#     Create a dependency that requires the user to have one of the specified roles.
#
#     This is a factory function that returns a dependency function.
#     Usage:
#         @router.get("/analytics")
#         async def analytics(
#             _: User = Depends(require_roles([UserRole.EXECUTIVE]))
#         ):
#             ...
#
#     Args:
#         allowed_roles: List of roles that are allowed to access the endpoint
#
#     Returns:
#         Dependency function that validates user role
#
#     Raises:
#         HTTPException: If user doesn't have required role (403) or is not authenticated (401)
#     """
#     def role_checker(user: User = Depends(get_current_user)) -> User:
#         """
#         Check if user has one of the allowed roles.
#
#         Args:
#             user: Current authenticated user
#
#         Returns:
#             User if authorized
#
#         Raises:
#             HTTPException: 403 if user doesn't have required role
#         """
#         # Check if user's role is in allowed roles
#         if user.role not in allowed_roles:
#             logger.warning(
#                 f"Access denied: User {user.id} with role {user.role} "
#                 f"attempted to access endpoint requiring {allowed_roles}"
#             )
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail=f"Access denied. Required roles: {[r for r in allowed_roles]}",
#             )
#
#         return user
#
#     return role_checker

# RBAC BYPASS - Returns a dummy user to allow all access
def require_roles(allowed_roles: List[UserRole]):
    """RBAC DISABLED - Returns dummy user to allow all access."""
    def role_checker(user: User = Depends(get_current_user)) -> User:
        """
            Get the user_id from the access_token
        """
        return user

    return role_checker


# RBAC DISABLED - All convenience functions now return dummy user
# Convenience dependencies for common role checks
# def require_manager(user: User = Depends(require_roles([UserRole.EXECUTIVE]))) -> User:
#     """
#     Require EXECUTIVE role (formerly MANAGER).
#
#     Usage:
#         @router.get("/analytics")
#         async def analytics(user: User = Depends(require_manager)):
#             ...
#     """
#     return user

def require_manager(user: User = Depends(require_roles([UserRole.EXECUTIVE]))) -> User:
    """RBAC DISABLED - Returns dummy user."""
    return user


# def require_csr(user: User = Depends(require_roles([UserRole.CSR]))) -> User:
#     """
#     Require CSR role.
#
#     Usage:
#         @router.get("/calls")
#         async def list_calls(user: User = Depends(require_csr)):
#             ...
#     """
#     return user

def require_csr(user: User = Depends(require_roles([UserRole.CSR]))) -> User:
    """RBAC DISABLED - Returns dummy user."""
    return user


# def require_sales_rep(user: User = Depends(require_roles([UserRole.SALES_REP]))) -> User:
#     """
#     Require SALES_REP role.
#
#     Usage:
#         @router.get("/deals")
#         async def list_deals(user: User = Depends(require_sales_rep)):
#             ...
#     """
#     return user

def require_sales_rep(user: User = Depends(require_roles([UserRole.SALES_REP]))) -> User:
    """RBAC DISABLED - Returns dummy user."""
    return user


# def require_manager_or_csr(
#     user: User = Depends(require_roles([UserRole.EXECUTIVE, UserRole.CSR]))
# ) -> User:
#     """
#     Require either EXECUTIVE (formerly MANAGER) or CSR role.
#
#     Usage:
#         @router.get("/calls")
#         async def list_calls(user: User = Depends(require_manager_or_csr)):
#             ...
#     """
#     return user

def require_manager_or_csr(
    user: User = Depends(require_roles([UserRole.EXECUTIVE, UserRole.CSR]))
) -> User:
    """RBAC DISABLED - Returns dummy user."""
    return user


# def require_manager_or_sales_rep(
#     user: User = Depends(require_roles([UserRole.EXECUTIVE, UserRole.SALES_REP]))
# ) -> User:
#     """
#     Require either EXECUTIVE (formerly MANAGER) or SALES_REP role.
#
#     Usage:
#         @router.get("/deals")
#         async def list_deals(user: User = Depends(require_manager_or_sales_rep)):
#             ...
#     """
#     return user

def require_manager_or_sales_rep(
    user: User = Depends(require_roles([UserRole.EXECUTIVE, UserRole.SALES_REP]))
) -> User:
    """RBAC DISABLED - Returns dummy user."""
    return user


# def require_executive(user: User = Depends(require_roles([UserRole.EXECUTIVE]))) -> User:
#     """
#     Require EXECUTIVE role.
#
#     Usage:
#         @router.get("/analytics")
#         async def analytics(user: User = Depends(require_executive)):
#             ...
#     """
#     return user

def require_executive(user: User = Depends(require_roles([UserRole.EXECUTIVE]))) -> User:
    """RBAC DISABLED - Returns dummy user."""
    return user


# def require_any_role(allowed_roles: List[UserRole]):
#     """
#     Create a dependency that requires one of the specified roles.
#
#     This is an alias for require_roles for clearer API naming.
#
#     Usage:
#         @router.get("/data")
#         async def get_data(
#             user: User = Depends(require_any_role([UserRole.CSR, UserRole.EXECUTIVE]))
#         ):
#             ...
#
#     Args:
#         allowed_roles: List of roles that are allowed
#
#     Returns:
#         Dependency function that validates user role
#     """
#     return require_roles(allowed_roles)

def require_any_role(allowed_roles: List[UserRole]):
    """RBAC DISABLED - Returns dummy user."""
    return require_roles(allowed_roles)

