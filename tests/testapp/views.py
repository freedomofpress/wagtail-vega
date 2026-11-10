from django.core.exceptions import ValidationError

from wagtail_vega.views import SourceRowsView

from .models import DONATION_GROUPS, DONATION_YEARS, donation_rows


class DonationRowsView(SourceRowsView):
    """The "donations" source's rows, for the admin (DonationsDatasetBlock's
    source_rows_urls)."""

    def get_rows(self, request):
        year = request.GET.get("year", "")
        if year not in dict(DONATION_YEARS):
            raise ValidationError("Choose a year.")
        group_by = request.GET.getlist("group_by")
        if unknown := set(group_by) - set(DONATION_GROUPS):
            raise ValidationError(f"Can't group by {', '.join(sorted(unknown))}.")
        rows = donation_rows(int(year), group_by)
        if not rows:
            raise ValidationError(f"There are no donations in {year}.")
        return rows
