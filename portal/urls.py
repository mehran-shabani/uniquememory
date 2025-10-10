from django.urls import path

from .views import ConsentManagementView

app_name = "portal"

urlpatterns = [
    path("consents/", ConsentManagementView.as_view(), name="consents"),
]
