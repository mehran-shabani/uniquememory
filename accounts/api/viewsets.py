from __future__ import annotations

from rest_framework import permissions, viewsets

from accounts.models import User

from .serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    """Basic CRUD viewset for managing users via the API."""

    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)
    queryset = User.objects.all().order_by("-date_joined")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return queryset
        return queryset.filter(id=user.id)
