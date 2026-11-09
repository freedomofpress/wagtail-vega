"""Create a demo page with example charts: python manage.py seed_sandbox"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from wagtail.models import Site

from tests.testapp.demo import create_demo_page
from tests.testapp.models import ChartPage


class Command(BaseCommand):
    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")

        ChartPage.objects.all().delete()
        site = Site.objects.get(is_default_site=True)
        site.hostname, site.port, site.site_name = "localhost", 8000, "sandbox"
        site.save()
        page = create_demo_page()
        self.stdout.write(self.style.SUCCESS(f"Seeded {page.url_path}; login admin/admin"))
