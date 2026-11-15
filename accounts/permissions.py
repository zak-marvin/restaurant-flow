from rest_framework.permissions import BasePermission


def role_required(*roles):
    """Factory: returns a permission class allowing only the given roles (admin always allowed)."""

    class _RolePermission(BasePermission):
        def has_permission(self, request, view):
            user = request.user
            return bool(
                user and user.is_authenticated and
                (user.role in roles or user.role == 'admin')
            )

    return _RolePermission


IsAdmin = role_required('admin')
IsWaiterOrAdmin = role_required('waiter', 'admin')
IsKitchenOrAdmin = role_required('kitchen', 'admin')
IsCashierOrAdmin = role_required('cashier', 'admin')
