from rest_framework.routers import DefaultRouter
from .views import AccountViewSet, VaultFileViewSet, MercadoPagoWebhookView, CreatePaymentView, UserProfileView
from django.urls import path

router = DefaultRouter()
router.register("cuentas", AccountViewSet, basename="cuentas")
router.register("files", VaultFileViewSet, basename="files")

urlpatterns = router.urls + [
    path('profile/me/',
         UserProfileView.as_view(), name='user-profile'),
    path('webhook/mercado-pago/',
         MercadoPagoWebhookView.as_view(), name='mp-webhook'),
    path('payment/create/',
         CreatePaymentView.as_view(), name='payment-create'),
]
