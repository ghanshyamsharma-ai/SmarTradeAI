from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def health(_request):
    return JsonResponse({"status": "ok", "service": "django-admin"})


urlpatterns = [
    path("health", health),
    path("admin/", admin.site.urls),
]
