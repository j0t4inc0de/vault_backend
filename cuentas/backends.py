# cuentas/backends.py

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class EmailBackend(ModelBackend):
    """
    Permite autenticar usuarios usando su email en lugar del username.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        try:
            # Buscamos al usuario cuyo email coincida con lo que escribieron
            # (aunque el campo se llame 'username', le pasaremos el email)
            user = UserModel.objects.get(email=username)
        except UserModel.DoesNotExist:
            return None

        if user.check_password(password):
            return user
        return None