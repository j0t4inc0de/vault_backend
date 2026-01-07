# cuentas/serializers.py

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
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
    # Agregamos la validación de email único aquí
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(
            queryset=User.objects.all(), message="Este correo ya está registrado.")]
    )
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'email')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data['email']
        )
        return user


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'username' in self.fields:
            del self.fields['username']

    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        email_ingresado = attrs.get('email')
        password_ingresado = attrs.get('password')

        if email_ingresado:
            attrs['username'] = email_ingresado

        # 3. Dejamos que el padre haga la autenticación mágica
        return super().validate(attrs)
