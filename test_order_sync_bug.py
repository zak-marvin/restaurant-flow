"""
Reproduces the real bug: an order's status got permanently stuck at
'pending'/'accepted' while every item underneath it was already
'served' — because the old sync logic only allowed a single legal step
forward per call, and an unaccepted order can't legally jump straight
to 'served'. This silently blocked cashier checkout, since it requires
order.status == 'served', not just the items.
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurantflow.settings')
django.setup()

from django.test import TestCase


class OrderSyncBugTest(TestCase):
    def setUp(self):
        from restaurant.models import Table
        from menu.models import Category, MenuItem
        from orders.models import Order, OrderItem

        self.table = Table.objects.create(number=90, capacity=4)
        cat = Category.objects.create(name='Sync Bug Test', sort_order=1)
        item1 = MenuItem.objects.create(name='Item One', price=10000, category=cat)
        item2 = MenuItem.objects.create(name='Item Two', price=10000, category=cat)

        # Order is left at PENDING — waiter never explicitly tapped Accept
        self.order = Order.objects.create(table=self.table, channel='waiter', status=Order.Status.PENDING)
        self.oi1 = OrderItem.objects.create(order=self.order, menu_item=item1, quantity=1, unit_price=10000)
        self.oi2 = OrderItem.objects.create(order=self.order, menu_item=item2, quantity=1, unit_price=10000)

    def test_order_no_longer_gets_stuck_when_items_outpace_accept(self):
        print("\n[Sync Bug] Order catches up to fully-served items despite never being explicitly accepted")

        # Kitchen + waiter race ahead without the order ever being "accepted"
        for item in (self.oi1, self.oi2):
            item.status = 'preparing'
            item.save()
        self.order.sync_status_from_items()
        self.assertEqual(self.order.status, 'preparing')
        print(f"  ✓ Order auto-caught-up to 'preparing' despite never being explicitly accepted")

        for item in (self.oi1, self.oi2):
            item.status = 'ready'
            item.save()
        self.order.sync_status_from_items()
        self.assertEqual(self.order.status, 'ready')

        for item in (self.oi1, self.oi2):
            item.status = 'served'
            item.save()
        self.order.sync_status_from_items()

        self.assertEqual(
            self.order.status, 'served',
            "BUG: order is stuck and doesn't reflect that every item is served — "
            "this is exactly what blocked cashier checkout."
        )
        print("  ✓ Order correctly reaches 'served' — no longer stuck")

    def test_finalized_orders_never_resurrected(self):
        print("[Sync Bug] Paid/cancelled orders are never overwritten by item sync")
        self.order.status = 'paid'
        self.order.save()
        for item in (self.oi1, self.oi2):
            item.status = 'preparing'  # nonsensical for a paid order, but shouldn't matter
            item.save()
        self.order.sync_status_from_items()
        self.assertEqual(self.order.status, 'paid')
        print("  ✓ Paid order stays paid regardless of item status changes")

    def test_repair_command_fixes_existing_stuck_orders(self):
        print("[Sync Bug] One-time repair command un-sticks existing bad data")
        from django.core.management import call_command
        from io import StringIO
        from orders.models import Order

        # Simulate the OLD buggy behavior having left this order stuck:
        # items are all served, but order.status manually forced back to
        # 'accepted' to simulate data already corrupted by the old bug.
        for item in (self.oi1, self.oi2):
            item.status = 'served'
            item.save()
        Order.objects.filter(id=self.order.id).update(status='accepted')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'accepted')  # confirm it's "stuck" first

        out = StringIO()
        call_command('fix_stuck_order_statuses', stdout=out)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'served')
        self.assertIn('Fixed 1 order', out.getvalue())
        print(f"  ✓ Repair command output: {out.getvalue().strip().splitlines()[-1]}")
