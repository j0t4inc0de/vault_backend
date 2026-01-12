# cuentas/serializers.py

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import User
from django.db.models import Sum
from django.db import transaction
from core.utils import encrypt_text, decrypt_text
from .models import VaultFile, Anuncio, Profile, Account

# --- Serializers que ya funcionaban bien ---

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
        # Manejo seguro en caso de que el perfil no exista aún
        try:
            profile = user.profile
        except AttributeError:
            raise serializers.ValidationError("El usuario no tiene un perfil asociado.")

        total_limit_gb = profile.plan.limite_gb_base + profile.extra_gb_almacenamiento
        total_limit_bytes = total_limit_gb * 1024 * 1024 * 1024

        used_bytes = VaultFile.objects.filter(user=user).aggregate(
            Sum('size_bytes'))['size_bytes__sum'] or 0

        if (used_bytes + value.size) > total_limit_bytes:
            raise serializers.ValidationError(
                f"Espacio insuficiente. Tienes {total_limit_gb}GB y estás intentando superar el límite.")

        return value


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


# --- Serializers corregidos para Auth y Registro ---

class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all(), message="Este correo ya está registrado.")]
    )
    password = serializers.CharField(write_only=True)

    # IMPORTANTE: write_only=True evita el error "AttributeError: 'User' object has no attribute..."
    # al intentar devolver la respuesta JSON.
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
        # 1. Extraemos los datos que NO van en el modelo User
        pregunta_raw = validated_data.pop('pregunta_seguridad')
        respuesta_raw = validated_data.pop('respuesta_seguridad')
        pin_raw = validated_data.pop('pin_boveda')

        # 2. Procesamiento de datos (Minúsculas y Encriptación)
        # Pregunta: Solo minúsculas, SIN encriptar
        pregunta_final = pregunta_raw.strip().lower()

        # Respuesta: Minúsculas Y Encriptada
        respuesta_lower = respuesta_raw.strip().lower()
        respuesta_enc = encrypt_text(respuesta_lower)

        # PIN: Encriptado
        pin_enc = encrypt_text(pin_raw)

        # Aseguramos que sea string si la función de encriptación devuelve bytes
        if isinstance(respuesta_enc, bytes): respuesta_enc = respuesta_enc.decode('utf-8')
        if isinstance(pin_enc, bytes): pin_enc = pin_enc.decode('utf-8')

        with transaction.atomic():
            # Creamos el usuario estándar
            user = User.objects.create_user(**validated_data)

            # Creamos el perfil con los datos procesados
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    'pregunta_seguridad': pregunta_final,
                    'respuesta_seguridad': respuesta_enc,
                    'pin_boveda': pin_enc
                }
            )
            
        return user


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Maneja el login con validación de contraseña + desafío de pregunta de seguridad.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Eliminamos el campo username del form por defecto si existe, ya que usamos email
        self.fields.pop('username', None)

    email = serializers.EmailField()
    password = serializers.CharField()
    security_answer = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        # Mapeamos email a username para que la clase padre pueda validar
        email_ingresado = attrs.get('email')
        if email_ingresado:
            attrs['username'] = email_ingresado

        # 1. Validar credenciales básicas (Email y Password)
        try:
            # Esto valida user/pass y devuelve los tokens si todo está bien
            # Nota: 'data' aquí contiene 'access' y 'refresh'
            data = super().validate(attrs)
        except Exception:
            raise ValidationError({"detail": "Credenciales inválidas (email o contraseña incorrectos)."})

        # 2. Validar Desafío de Seguridad (MFA simple)
        user = self.user
        try:
            profile = user.profile
        except Profile.DoesNotExist:
            # Si es un superusuario antiguo sin perfil, lo dejamos pasar
            return data

        # Obtenemos la respuesta enviada por el usuario (y la pasamos a minúsculas)
        respuesta_usuario = attrs.get('security_answer', '').strip().lower()

        # Obtenemos la respuesta real de la BD, desencriptamos y pasamos a minúsculas
        try:
            respuesta_real_raw = decrypt_text(profile.respuesta_seguridad)
            respuesta_real = respuesta_real_raw.strip().lower() if respuesta_real_raw else ""
        except Exception:
            # Si falla la desencriptación, no podemos validar, dejamos pasar o bloqueamos (aquí dejamos pasar por seguridad de no bloquear al usuario por error de sistema)
            return data

        # 3. Lógica de comparación
        if not respuesta_usuario:
            # CASO A: El frontend aún no ha pedido la respuesta, devolvemos error especial con la pregunta
            raise ValidationError({
                "code": "mfa_required",
                "detail": "Se requiere respuesta de seguridad",
                # La pregunta se guardó en minúsculas, se envía tal cual
                "question": profile.pregunta_seguridad 
            })

        if respuesta_usuario != respuesta_real:
            # CASO B: El usuario envió una respuesta pero es incorrecta
            raise ValidationError({
                "code": "mfa_failed",
                "detail": "La respuesta de seguridad es incorrecta."
            })

        # Si todo coincide, devolvemos los tokens
        return data