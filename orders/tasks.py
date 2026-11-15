"""
Celery task: detect tables where an order has been READY/SERVED for a while
with no payment started (a likely 'walkout' or just a slow cashier) and
flag the table 'awaiting_payment' so staff get a visual nudge on the
Tables screen. Requires a running Redis broker + celery worker + celery beat.
"""
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from .models import Order


STALE_AFTER_MINUTES = 30


@shared_task
def flag_stale_orders():
    cutoff = timezone.now() - timedelta(minutes=STALE_AFTER_MINUTES)
    stale_orders = Order.objects.filter(
        status=Order.Status.SERVED, updated_at__lt=cutoff
    ).select_related('table')

    flagged_tables = set()
    for order in stale_orders:
        table = order.table
        if table.status != table.Status.AWAITING_PAYMENT:
            table.status = table.Status.AWAITING_PAYMENT
            table.save(update_fields=['status'])
            flagged_tables.add(table.number)
    return f"Flagged tables: {sorted(flagged_tables)}"
