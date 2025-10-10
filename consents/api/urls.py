from rest_framework.routers import DefaultRouter

from .views import ConsentViewSet

router = DefaultRouter()
router.register(r"", ConsentViewSet, basename="consent")

urlpatterns = router.urls
