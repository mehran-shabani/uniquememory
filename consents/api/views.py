from __future__ import annotations

from rest_framework import permissions, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from consents.models import Consent

from .serializers import ConsentSerializer


class ConsentViewSet(viewsets.ModelViewSet):
    serializer_class = ConsentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        return Consent.objects.filter(user=self.request.user).order_by("-updated_at")

    def perform_create(self, serializer: ConsentSerializer) -> None:
        serializer.save()

    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request, *args, **kwargs):
        consent = self.get_object()
        consent.revoke()
        serializer = self.get_serializer(consent)
        return Response(serializer.data, status=status.HTTP_200_OK)
