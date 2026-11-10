from django.urls import path
from wagtail import hooks

from .views import DonationRowsView


@hooks.register("register_admin_urls")
def register_admin_urls():
    return [
        path("donation-rows/", DonationRowsView.as_view(), name="testapp_donation_rows"),
    ]
