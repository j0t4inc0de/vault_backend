import uuid
from django.db import models
from django.contrib.auth.models import User
import os


class VaultFile(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="vault/%Y/%m/")
    name = models.CharField(max_length=255)
    # Guardamos el peso para sumar rápido
    size_bytes = models.BigIntegerField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Auto-guardar el tamaño del archivo al crearlo
        if self.file and not self.size_bytes:
            self.size_bytes = self.file.size
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PlanConfig(models.Model):
    """Control de planes: Estándar, Premium, etc."""
    nombre = models.CharField(max_length=50, unique=True)
    precio_mensual = models.DecimalField(
        max_digits=10, decimal_places=0, default=0)
    slots_cuentas_base = models.IntegerField(default=10)
    limite_gb_base = models.FloatField(default=2.0)
    slots_notas_base = models.IntegerField(default=5)
    slots_recordatorios_base = models.IntegerField(default=1)
    permite_sincronizacion_calendario = models.BooleanField(default=False)
    sin_anuncios = models.BooleanField(default=False)

    def __str__(self):
        return f"Plan {self.nombre} (${self.precio_mensual})"


class PackConfig(models.Model):
    """Control de Packs: Pack 4k, Pack 10k, etc."""
    nombre = models.CharField(max_length=100)
    precio = models.DecimalField(max_digits=10, decimal_places=0)
    extra_slots_cuentas = models.IntegerField(default=0)
    extra_gb = models.FloatField(default=0)
    extra_notas = models.IntegerField(default=0)
    extra_recordatorios = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.nombre} (${self.precio})"


class Profile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile")
    plan = models.ForeignKey(
        PlanConfig, on_delete=models.SET_NULL, null=True, blank=True)

    # Seguridad
    pregunta_seguridad = models.CharField(
        max_length=255, null=True, blank=True)
    respuesta_seguridad = models.CharField(
        max_length=255, null=True, blank=True)
    pin_boveda = models.CharField(
        max_length=128, null=True, blank=True)  # Encriptado

    # Acumuladores (Lo que compra o gana el usuario)
    extra_slots_cuentas = models.IntegerField(default=0)
    extra_gb_almacenamiento = models.FloatField(default=0)
    extra_slots_notas = models.IntegerField(default=0)
    extra_slots_recordatorios = models.IntegerField(default=0)

    # Métricas para el Dashboard
    total_anuncios_vistos = models.IntegerField(default=0)
    anuncios_vistos_hoy = models.IntegerField(default=0)
    ultima_vez_anuncio = models.DateTimeField(null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Perfil de {self.user.username}"

    @property
    def total_cuentas_permitidas(self):
        base = self.plan.slots_cuentas_base if self.plan else 10
        return base + self.extra_slots_cuentas


class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="accounts")

    email = models.EmailField()
    password_encrypted = models.TextField()
    secret_encrypted = models.TextField(blank=True, null=True)

    site_url = models.URLField(blank=True, null=True)
    site_name = models.CharField(max_length=100, blank=True, null=True)
    site_icon_url = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.site_name or self.email}"
