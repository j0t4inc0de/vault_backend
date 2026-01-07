# cuentas/serializers.py

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Account
from core.utils import encrypt_text, decrypt_text


class AccountSerializer(serializers.ModelSerializer):
    # Campos de escritura (lo que envía el usuario)
    password = serializers.CharField(write_only=True, required=False)
    secret = serializers.CharField(
        write_only=True, required=False)  # <--- NUEVO

    # Campos de lectura (lo que devolvemos)
    decrypted_password = serializers.SerializerMethodField()
    decrypted_secret = serializers.SerializerMethodField()  # <--- NUEVO

    class Meta:
        model = Account
        # Excluimos los campos internos de encriptación y el usuario
        exclude = ("user", "password_encrypted", "secret_encrypted")

    def get_decrypted_password(self, obj):
        return decrypt_text(obj.password_encrypted)

    def get_decrypted_secret(self, obj):  # <--- NUEVO
        return decrypt_text(obj.secret_encrypted)

    def create(self, validated_data):
        password_raw = validated_data.pop('password', None)
        secret_raw = validated_data.pop('secret', None)  # <--- NUEVO

        if password_raw:
            validated_data['password_encrypted'] = encrypt_text(password_raw)
        if secret_raw:  # <--- NUEVO
            validated_data['secret_encrypted'] = encrypt_text(secret_raw)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        password_raw = validated_data.pop('password', None)
        secret_raw = validated_data.pop('secret', None)  # <--- NUEVO

        if password_raw:
            validated_data['password_encrypted'] = encrypt_text(password_raw)
        if secret_raw:  # <--- NUEVO
            validated_data['secret_encrypted'] = encrypt_text(secret_raw)

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
