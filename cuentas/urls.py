from rest_framework.routers import DefaultRouter
from .views import AccountViewSet

router = DefaultRouter()
router.register("cuentas", AccountViewSet, basename="cuentas")

urlpatterns = router.urls
