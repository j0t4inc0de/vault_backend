# cuentas/serializers.py

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import User
from django.db.models import Sum
from core.utils import encrypt_text, decrypt_text
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
        profile = user.profile

        # 1. Calcular límite total del usuario en Bytes
        # (Base del plan + Extras comprados) * 1GB (1024^3 bytes)
        total_limit_gb = profile.plan.limite_gb_base + profile.extra_gb_almacenamiento
        total_limit_bytes = total_limit_gb * 1024 * 1024 * 1024

        # 2. Calcular cuánto lleva usado
        used_bytes = VaultFile.objects.filter(user=user).aggregate(
            Sum('size_bytes'))['size_bytes__sum'] or 0

        # 3. Validar si el nuevo archivo cabe
        if (used_bytes + value.size) > total_limit_bytes:
            raise serializers.ValidationError(
                f"Espacio insuficiente. Tienes {total_limit_gb}GB y estás intentando superar el límite.")

        return value


class AccountSerializer(serializers.ModelSerializer):
    # Campos de escritura (lo que envía el usuario)
    password = serializers.CharField(write_only=True, required=False)
    secret = serializers.CharField(
        write_only=True, required=False, allow_blank=True, allow_null=True)

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
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(
            queryset=User.objects.all(), message="Este correo ya está registrado.")]
    )
    password = serializers.CharField(write_only=True)

    pregunta_seguridad = serializers.CharField(required=True)
    respuesta_seguridad = serializers.CharField(write_only=True, required=True)
    pin_boveda = serializers.CharField(
        write_only=True, required=True, min_length=4, max_length=8)

    class Meta:
        model = User
        fields = ('username', 'password', 'email',
                  'pregunta_seguridad', 'respuesta_seguridad', 'pin_boveda')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data['email']
        )

        profile, created = Profile.objects.get_or_create(user=user)

        profile.pregunta_seguridad = validated_data['pregunta_seguridad']
        profile.respuesta_seguridad = encrypt_text(
            validated_data['respuesta_seguridad'])
        profile.pin_boveda = encrypt_text(validated_data['pin_boveda'])

        profile.save()

        return user


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'username' in self.fields:
            del self.fields['username']

    email = serializers.EmailField()
    password = serializers.CharField()
    security_answer = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        email_ingresado = attrs.get('email')
        if email_ingresado:
            attrs['username'] = email_ingresado

        try:
            data = super().validate(attrs)
        except Exception as e:
            raise ValidationError({"detail": "Credenciales inválidas."})

        user = self.user
        try:
            profile = user.profile
        except Profile.DoesNotExist:
            return data

        respuesta_usuario = attrs.get('security_answer', '').strip()

        try:
            respuesta_real = decrypt_text(profile.respuesta_seguridad)
        except:
            return data

        if not respuesta_usuario:
            # CASO A: El usuario no envió respuesta, le devolvemos la pregunta.
            raise ValidationError({
                "code": "mfa_required",
                "detail": "Se requiere respuesta de seguridad",
                "question": profile.pregunta_seguridad
            })

        # CASO B: El usuario envió respuesta, comparamos (insensible a mayúsculas)
        if respuesta_usuario.lower() != respuesta_real.lower():
            raise ValidationError({
                "code": "mfa_failed",
                "detail": "La respuesta de seguridad es incorrecta."
            })

        # Si todo sale bien, devolvemos el token
        return data
