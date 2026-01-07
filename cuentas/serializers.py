# cuentas/serializers.py

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Account
from core.utils import encrypt_text, decrypt_text


class AccountSerializer(serializers.ModelSerializer):
    # Creamos un campo "falso" para recibir la contraseña sin encriptar del usuario
    password = serializers.CharField(write_only=True, required=False)

    # Creamos un campo para devolver la contraseña desencriptada al leer
    decrypted_password = serializers.SerializerMethodField()

    class Meta:
        model = Account
        # Excluimos user (seguridad) y password_encrypted (porque lo manejamos internamente)
        exclude = ("user", "password_encrypted")

    def get_decrypted_password(self, obj):
        # Cuando el frontend pide los datos, desencriptamos al vuelo
        return decrypt_text(obj.password_encrypted)

    def create(self, validated_data):
        # Sacamos la contraseña plana del formulario
        password_raw = validated_data.pop('password', None)

        # Si nos dieron una contraseña, la encriptamos antes de guardar
        if password_raw:
            validated_data['password_encrypted'] = encrypt_text(password_raw)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Lo mismo para cuando actualizamos una cuenta
        password_raw = validated_data.pop('password', None)

        if password_raw:
            validated_data['password_encrypted'] = encrypt_text(password_raw)

        return super().update(instance, validated_data)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'email')

    def create(self, validated_data):
        # create_user se encarga de hashear la contraseña automáticamente
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email', '')
        )
        return user
