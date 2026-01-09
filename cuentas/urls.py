from rest_framework.routers import DefaultRouter
from .views import AccountViewSet, VaultFileViewSet, MercadoPagoWebhookView
from django.urls import path

router = DefaultRouter()
router.register("cuentas", AccountViewSet, basename="cuentas")
router.register("files", VaultFileViewSet, basename="files")

urlpatterns = router.urls + [
    # Agregamos la ruta del webhook
    path('webhook/mercado-pago/',
         MercadoPagoWebhookView.as_view(), name='mp-webhook'),
]
