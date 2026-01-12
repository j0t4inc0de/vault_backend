import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from urllib.parse import urlparse

import os


class Anuncio(models.Model):
    OPCIONES_TIPO = [
        ('info', 'Información'),
        ('promo', 'Promoción / Pack'),
        ('alerta', 'Alerta / Pánico'),
    ]

    titulo = models.CharField(max_length=150)
    mensaje = models.TextField(help_text="Puedes usar saltos de línea.")
    creado_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField(
        help_text="Fecha y hora en que dejará de mostrarse el anuncio.")
    tipo = models.CharField(
        max_length=20, choices=OPCIONES_TIPO, default='info')
    activo = models.BooleanField(
        default=True, help_text="Desactívalo manualmente si quieres ocultarlo antes de tiempo.")

    class Meta:
        ordering = ['-creado_en']
        verbose_name = "📢 Anuncio de Sistema"
        verbose_name_plural = "📢 Anuncios de Sistema"

    def __str__(self):
        return f"{self.titulo} (Expira: {self.expira_en})"


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
    site_icon_url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Lógica: Si el usuario puso una URL del sitio, pero NO subió un icono propio
        if self.site_url and not self.site_icon_url:
            try:
                # 1. Limpiamos la URL para obtener solo el dominio limpio
                # Ej: "https://www.netflix.com/login" -> "www.netflix.com"
                parsed = urlparse(self.site_url)

                # Manejo robusto: Si el usuario puso "google.com" sin https://,
                # urlparse lo pone en 'path', no en 'netloc'.
                domain = parsed.netloc if parsed.netloc else parsed.path.split(
                    '/')[0]

                if domain:
                    # 2. Generamos la URL del servicio de iconos de Google en HD (128px)
                    self.site_icon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"

            except Exception as e:
                # Si algo falla, no rompemos el guardado, simplemente no ponemos icono
                print(f"No se pudo generar el icono: {e}")

        # Guardamos normalmente
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.site_name or self.email}"
