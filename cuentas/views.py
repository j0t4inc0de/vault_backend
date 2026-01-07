# cuentas/views.py

from rest_framework import viewsets, generics
from rest_framework.permissions import IsAuthenticated, AllowAny # Importar AllowAny
from .models import Account
from .serializers import AccountSerializer, RegisterSerializer # Importar el nuevo serializador
from django.contrib.auth.models import User

class AccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AccountSerializer

    def get_queryset(self):
        return Account.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,) # Permitir acceso público
    serializer_class = RegisterSerializer