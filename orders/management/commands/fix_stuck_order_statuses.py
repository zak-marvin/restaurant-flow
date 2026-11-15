"""
One-time repair: recomputes order status from item status for every
active order. Run this once after deploying the sync_status_from_items
fix, to un-stick any orders that got frozen by the old bug (order stuck
at 'accepted' while every item underneath already says 'served').

Usage:
    python manage.py fix_stuck_order_statuses
"""
from django.core.management.base import BaseCommand
from orders.models import Order


class Command(BaseCommand):
    help = "One-time: recomputes order status from item status for every active order."

    def handle(self, *args, **options):
        active_orders = Order.objects.exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED])
        fixed = 0
        for order in active_orders:
            old_status = order.status
            order.sync_status_from_items()
            if order.status != old_status:
                fixed += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Order #{order.id} (Table {order.table.number}): {old_status} -> {order.status}")
                )
        if fixed == 0:
            self.stdout.write("No stuck orders found — everything already matches.")
        else:
            self.stdout.write(self.style.SUCCESS(f"\nFixed {fixed} order(s)."))
