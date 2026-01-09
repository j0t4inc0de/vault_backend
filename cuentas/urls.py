from rest_framework.routers import DefaultRouter
from .views import AccountViewSet, VaultFileViewSet

router = DefaultRouter()
router.register("cuentas", AccountViewSet, basename="cuentas")
router.register("files", VaultFileViewSet, basename="files")
urlpatterns = router.urls
