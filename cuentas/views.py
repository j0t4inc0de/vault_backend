# cuentas/views.py

from rest_framework import viewsets, generics, filters
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import EmailTokenObtainPairSerializer
from .models import Account
from .serializers import AccountSerializer, RegisterSerializer
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from .permissions import IsAccountOwnerAndWithinLimit


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class AccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAccountOwnerAndWithinLimit]

    serializer_class = AccountSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['site_name', 'site_url', 'email']

    def get_queryset(self):
        # El usuario siempre puede VER todas sus cuentas, incluso las congeladas.
        return Account.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        asunto = 'Bienvenido a Niun - Tu seguridad es primero'
        mensaje = f"""Hola {user.username}, 

Bienvenido a Niun.
Ya tienes tu cuenta lista para guardar contraseñas, notas y recordatorios.
Ni un olvido, ni un problema.

Atentamente,
Juan Erices.
"""
        remitente = settings.EMAIL_HOST_USER
        destinatario = [user.email]

        # 3. Enviar el correo
        try:
            print(f"Intentando enviar correo a {user.email}...")
            send_mail(asunto, mensaje, remitente,
                      destinatario, fail_silently=False)
            print("✅ Correo enviado con éxito.")
        except Exception as e:
            print(f"❌ Error al enviar el correo: {e}")
