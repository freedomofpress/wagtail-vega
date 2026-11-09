from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder


class VegaJSONEncoder(DjangoJSONEncoder):
    """Like DjangoJSONEncoder, but Decimals become numbers (Vega needs
    numbers, not strings, for quantitative fields)."""

    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)
