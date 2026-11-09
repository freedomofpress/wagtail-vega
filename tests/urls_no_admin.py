"""A URLconf without the Wagtail admin, for widget tests."""

from django.urls import include, path
from wagtail import urls as wagtail_urls

urlpatterns = [path("", include(wagtail_urls))]
