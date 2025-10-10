from django.urls import path

from .views import (
    MemoryEntryCollectionApiView,
    MemoryEntryDetailApiView,
    MemoryEntryDetailView,
    MemoryEntryListView,
)

app_name = "memory"

urlpatterns = [
    path("", MemoryEntryListView.as_view(), name="entry-list"),
    path("<int:pk>/", MemoryEntryDetailView.as_view(), name="entry-detail"),
    path("api/", MemoryEntryCollectionApiView.as_view(), name="entry-collection-api"),
    path("api/<int:pk>/", MemoryEntryDetailApiView.as_view(), name="entry-detail-api"),
]
