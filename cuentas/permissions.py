from rest_framework import permissions
from .models import Account


class IsAccountOwnerAndWithinLimit(permissions.BasePermission):
    """
    Maneja la lógica del 'Efecto Congelador':
    1. Bloquea CREAR (POST) si el usuario ya llenó su cupo.
    2. Bloquea EDITAR/BORRAR (PUT, PATCH, DELETE) si la cuenta específica
       quedó fuera del límite tras un downgrade (es decir, es de solo lectura).
    """
    message = "Límite de plan excedido."

    def has_permission(self, request, view):
        if request.method == 'POST':
            profile = request.user.profile
            # Contamos cuántas tiene actualmente
            current_count = Account.objects.filter(user=request.user).count()

            if current_count >= profile.total_cuentas_permitidas:
                self.message = f"Has alcanzado tu límite de {profile.total_cuentas_permitidas} cuentas. Sube de nivel para seguir agregando."
                return False

        # Para listar (GET) u otros, dejamos pasar (la vista filtra por usuario)
        return True

    def has_object_permission(self, request, view, obj):
        # Primero validamos que sea el dueño
        if obj.user != request.user:
            return False

        # Si es método seguro (GET, HEAD, OPTIONS), permitimos leer siempre.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Si intenta escribir (PUT, PATCH, DELETE), verificamos si ESTA cuenta es editable
        profile = request.user.profile
        limit = profile.total_cuentas_permitidas

        # Obtenemos los IDs de las 'N' cuentas más antiguas (las que entran en el plan)
        # Esto define cuáles se salvan del congelamiento.
        editable_ids = Account.objects.filter(user=request.user)\
                                      .order_by('created_at')\
                                      .values_list('id', flat=True)[:limit]

        if obj.id not in editable_ids:
            self.message = "Esta cuenta está congelada (Solo Lectura) porque excede tu límite actual."
            return False

        return True
