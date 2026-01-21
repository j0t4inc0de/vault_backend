# cuentas/serializers.py

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Sum
from django.db import transaction
from core.utils import encrypt_text, decrypt_text, encrypt_bytes
from .models import VaultFile, Anuncio, Profile, Account

class AnuncioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Anuncio
        fields = ['id', 'titulo', 'mensaje', 'creado_en', 'expira_en', 'tipo']


class VaultFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = VaultFile
        fields = ['id', 'name', 'file', 'size_bytes', 'created_at']
        read_only_fields = ['size_bytes', 'created_at']

    def validate_file(self, value):
        user = self.context['request'].user
        LIMIT_MB = 50
        if value.size > LIMIT_MB * 1024 * 1024:
            raise serializers.ValidationError(f"El archivo excede el límite de {LIMIT_MB}MB para cifrado seguro.")

        profile = user.profile

        total_limit_gb = profile.plan.limite_gb_base + profile.extra_gb_almacenamiento
        total_limit_bytes = total_limit_gb * 1024 * 1024 * 1024

        used_bytes = VaultFile.objects.filter(user=user).aggregate(
            Sum('size_bytes'))['size_bytes__sum'] or 0

        if (used_bytes + value.size) > total_limit_bytes:
            raise serializers.ValidationError(
                f"Espacio insuficiente. Tienes {total_limit_gb}GB y estás intentando superar el límite.")

        return value
    
    def create(self, validated_data):
        uploaded_file = validated_data.pop('file')
        user = self.context['request'].user

        file_bytes = uploaded_file.read()
        encrypted_bytes = encrypt_bytes(file_bytes)

        encrypted_file = ContentFile(encrypted_bytes, name=f"{uploaded_file.name}.enc")

        return VaultFile.objects.create(
            user=user,
            file=encrypted_file,
            name=uploaded_file.name,
            size_bytes=uploaded_file.size
        )


class AccountSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    secret = serializers.CharField(
        write_only=True, required=False, allow_blank=True, allow_null=True)

    decrypted_password = serializers.SerializerMethodField()
    decrypted_secret = serializers.SerializerMethodField()

    class Meta:
        model = Account
        exclude = ("user", "password_encrypted", "secret_encrypted")

    def get_decrypted_password(self, obj):
        return decrypt_text(obj.password_encrypted)

    def get_decrypted_secret(self, obj):
        return decrypt_text(obj.secret_encrypted)

    def create(self, validated_data):
        password_raw = validated_data.pop('password', None)
        secret_raw = validated_data.pop('secret', None)

        if password_raw:
            validated_data['password_encrypted'] = encrypt_text(password_raw)
        if secret_raw:
            validated_data['secret_encrypted'] = encrypt_text(secret_raw)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        password_raw = validated_data.pop('password', None)
        secret_raw = validated_data.pop('secret', None)

        if password_raw:
            validated_data['password_encrypted'] = encrypt_text(password_raw)
        if secret_raw:
            validated_data['secret_encrypted'] = encrypt_text(secret_raw)

        return super().update(instance, validated_data)


# --- Serializers para Auth y Registro ---

class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all(), message="Este correo ya está registrado.")]
    )
    password = serializers.CharField(write_only=True)

    pregunta_seguridad = serializers.CharField(write_only=True, required=True)
    respuesta_seguridad = serializers.CharField(write_only=True, required=True)
    pin_boveda = serializers.CharField(write_only=True, required=True, min_length=4, max_length=4)

    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'pregunta_seguridad', 'respuesta_seguridad', 'pin_boveda')

    def validate_pin_boveda(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("El PIN debe contener solo números.")
        return value

    def create(self, validated_data):
        pregunta_raw = validated_data.pop('pregunta_seguridad')
        respuesta_raw = validated_data.pop('respuesta_seguridad')
        pin_raw = validated_data.pop('pin_boveda')

        pregunta_final = pregunta_raw.strip().lower()

        respuesta_lower = respuesta_raw.strip().lower()
        
        respuesta_hash = make_password(respuesta_lower)
        pin_hash = make_password(pin_raw)

        if isinstance(respuesta_hash, bytes): respuesta_hash = respuesta_hash.decode('utf-8')
        if isinstance(pin_hash, bytes): pin_hash = pin_hash.decode('utf-8')

        with transaction.atomic():
            user = User.objects.create_user(**validated_data)

            Profile.objects.update_or_create(
                user=user,
                defaults={
                    'pregunta_seguridad': pregunta_final,
                    'respuesta_seguridad': respuesta_hash,
                    'pin_boveda': pin_hash,
                    'intentos_fallidos': 0
                }
            )
            
        return user


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    
    email = serializers.EmailField()
    password = serializers.CharField()
    security_answer = serializers.CharField(required=True) 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('username', None)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        security_answer = attrs.get('security_answer', '').strip().lower()
        try:
            user = User.objects.get(email=email)
            profile = user.profile
        except User.DoesNotExist:
            raise AuthenticationFailed("Credenciales inválidas.")
        except Profile.DoesNotExist:
            raise AuthenticationFailed("Error de cuenta: Perfil no configurado.")

        def registrar_fallo_y_salir():
            profile.intentos_fallidos += 1
            profile.save()

            if profile.intentos_fallidos >= 10:
                user.delete()
                raise AuthenticationFailed(
                    "Has excedido el límite de 10 intentos de seguridad. "
                    "Tu cuenta y todos tus datos han sido eliminados permanentemente por seguridad."
                )
            
            intentos_restantes = 10 - profile.intentos_fallidos
            raise AuthenticationFailed(
                f"Credenciales o respuesta incorrecta. "
                f"Te quedan {intentos_restantes} intentos antes de que se elimine la cuenta."
            )

        if not user.check_password(password):
            registrar_fallo_y_salir()

        if not check_password(security_answer, profile.respuesta_seguridad):
            registrar_fallo_y_salir()

        if not user.is_active:
            raise AuthenticationFailed("Esta cuenta está desactivada.")

        if profile.intentos_fallidos > 0:
            profile.intentos_fallidos = 0
            profile.save()

        refresh = self.get_token(user)

        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username
            }
        }