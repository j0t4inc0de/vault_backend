from django.contrib import admin
from django.db.models import Sum, Count
from django.utils.timezone import now
from .models import Account, Profile, PlanConfig, PackConfig, Anuncio

@admin.register(Anuncio)
class AnuncioAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'fecha_creacion') 
    
    list_filter = ('fecha_creacion',)

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
    list_display = ('user', 'plan', 'total_cuentas_permitidas',
                    'total_anuncios_vistos', 'fecha_registro')
    list_filter = ('plan', 'fecha_registro')
    search_fields = ('user__username', 'user__email')


class Dashboard(Profile):
    class Meta:
        proxy = True
        verbose_name = '📊 Métrica de Negocio'
        verbose_name_plural = '📊 DASHBOARD Y MÉTRICAS'


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

        # Enviamos los datos al Dashboard
        extra_context = extra_context or {}
        extra_context['summary'] = {
            'total': total_usuarios,
            'premium': usuarios_premium,
            'estandar': usuarios_estandar,
            'nuevos': nuevos_mes,
            'ads': total_ads,
            'ingresos': f"${ingresos_mrr:,.0f} CLP",
        }

        return super().changelist_view(request, extra_context=extra_context)

    change_list_template = "admin/dashboard_summary.html"


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'email', 'user', 'created_at')
    search_fields = ('site_name', 'email', 'user__username')
