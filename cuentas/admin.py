from django.contrib import admin
from django.db.models import Sum, Count
from django.utils.timezone import now
from .models import Account, Profile, PlanConfig, PackConfig, Anuncio, VaultFile


@admin.register(Anuncio)
class AnuncioAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'creado_en', 'activo')

    list_filter = ('creado_en', 'activo')

    search_fields = ('titulo', 'mensaje')


@admin.register(PlanConfig)
class PlanConfigAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio_mensual',
                    'slots_cuentas_base', 'limite_gb_base', 'sin_anuncios')
    list_editable = ('precio_mensual', 'slots_cuentas_base',
                     'limite_gb_base', 'sin_anuncios')


@admin.register(PackConfig)
class PackConfigAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio', 'extra_slots_cuentas', 'extra_gb')
    list_editable = ('precio', 'extra_slots_cuentas', 'extra_gb')


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Información de Suscripción / Límites'


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'uso_almacenamiento', 'total_cuentas_permitidas',
                    'total_anuncios_vistos', 'fecha_registro')
    list_filter = ('plan', 'fecha_registro')
    search_fields = ('user__username', 'user__email')
    
    def uso_almacenamiento(self, obj):
        # Sumar bytes de todos los archivos del usuario
        used_bytes = VaultFile.objects.filter(user=obj.user).aggregate(
            Sum('size_bytes'))['size_bytes__sum'] or 0
        
        # Convertir a MB para visualización
        used_mb = round(used_bytes / (1024 * 1024), 2)

        # Calcular límite total (Plan Base + Extras)
        base_gb = obj.plan.limite_gb_base if obj.plan else 0
        total_gb = base_gb + obj.extra_gb_almacenamiento
        
        return f"{used_mb} MB / {total_gb} GB"
    
    uso_almacenamiento.short_description = "Almacenamiento (Usado / Total)"


class Dashboard(Profile):
    class Meta:
        proxy = True
        verbose_name = 'Métrica de Negocio'
        verbose_name_plural = 'DASHBOARD Y MÉTRICAS'


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        # 1. Cálculos de Usuarios
        total_usuarios = Profile.objects.count()
        usuarios_premium = Profile.objects.filter(
            plan__precio_mensual__gt=0).count()
        usuarios_estandar = total_usuarios - usuarios_premium

        # 2. Usuarios nuevos este mes
        mes_actual = now().month
        nuevos_mes = Profile.objects.filter(
            fecha_registro__month=mes_actual).count()

        # 3. Métricas de Anuncios
        total_ads = Profile.objects.aggregate(Sum('total_anuncios_vistos'))[
            'total_anuncios_vistos__sum'] or 0

        # 4. Ingresos Estimados (MRR - Monthly Recurring Revenue)
        ingresos_mrr = Profile.objects.filter(plan__isnull=False).aggregate(
            Sum('plan__precio_mensual'))['plan__precio_mensual__sum'] or 0

        total_bytes_app = VaultFile.objects.aggregate(
            Sum('size_bytes'))['size_bytes__sum'] or 0

        # Convertir a GB
        total_gb_app = total_bytes_app / (1024 * 1024 * 1024)
        if total_gb_app < 1:
            # Si es menos de 1 GB, mostrar en MB
            total_storage_display = f"{total_bytes_app / (1024 * 1024):.2f} MB"
        else:
            total_storage_display = f"{total_gb_app:.2f} GB"

        # Tasa de Conversion a Premium
        conversion_rate = 0
        if total_usuarios > 0:
            conversion_rate = (usuarios_premium / total_usuarios) * 100

        # Demanda de Extras
        extras_stats = Profile.objects.aggregate(
            total_slots=Sum('extra_slots_cuentas'),
            total_gb=Sum('extra_gb_almacenamiento')
        )
        extra_slots = extras_stats['total_slots'] or 0
        extra_gb = extras_stats['total_gb'] or 0

        # Enviamos los datos al Dashboard
        extra_context = extra_context or {}
        extra_context['summary'] = {
            'total': total_usuarios,
            'premium': usuarios_premium,
            'estandar': usuarios_estandar,
            'nuevos': nuevos_mes,
            'ads': total_ads,
            'ingresos': f"${ingresos_mrr:,.0f} CLP",
            'storage': total_storage_display,
            'conversion': f"{conversion_rate:.1f}%",
            'extra_slots': extra_slots,
            'extra_gb': round(extra_gb, 1),
        }

        return super().changelist_view(request, extra_context=extra_context)

    change_list_template = "admin/dashboard_summary.html"


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'email', 'user', 'created_at')
    search_fields = ('site_name', 'email', 'user__username')
