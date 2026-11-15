import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurantflow.settings')
django.setup()

from django.test import TestCase, Client

class CheckoutTest(TestCase):
    def setUp(self):
        from accounts.models import User
        from restaurant.models import Table
        from menu.models import Category, MenuItem
        from orders.models import Order, OrderItem

        self.client = Client()
        self.cashier = User.objects.create(username='co_cashier', role='cashier')
        self.cashier.set_password('pass1234')
        self.cashier.save()
        self.waiter = User.objects.create(username='co_waiter', role='waiter')
        self.waiter.set_password('pass1234')
        self.waiter.save()

        self.table = Table.objects.create(number=60, capacity=4)
        self.table.status = 'occupied'
        self.table.save()

        cat = Category.objects.create(name='Checkout Test', sort_order=1)
        burger = MenuItem.objects.create(name='Checkout Burger', price=20000, category=cat)
        chips = MenuItem.objects.create(name='Checkout Chips', price=8000, category=cat)

        self.order = Order.objects.create(table=self.table, channel='waiter', status='served')
        OrderItem.objects.create(order=self.order, menu_item=burger, quantity=2, unit_price=20000, status='served')
        OrderItem.objects.create(order=self.order, menu_item=chips, quantity=1, unit_price=8000, status='served')
        # total should be 48000

    def test_login_restricted_to_cashier_role(self):
        print("\n[Checkout] Role restriction")
        r = self.client.post('/checkout/login/', {'username': 'co_waiter', 'password': 'pass1234'})
        self.client.logout()
        r2 = self.client.post('/checkout/login/', {'username': 'co_cashier', 'password': 'pass1234'})
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r2.url, '/checkout/')
        print("  ✓ Cashier login succeeds, redirected to board")

    def test_full_settle_flow(self):
        print("[Checkout] Full settle flow")
        self.client.post('/checkout/login/', {'username': 'co_cashier', 'password': 'pass1234'})

        r = self.client.get('/checkout/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Table 60')
        self.assertContains(r, 'Checkout Burger')
        print("  ✓ Board shows Table 60 with its bill")

        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {'method': 'cash', 'amount_tendered': '48000'})
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['amount'], '48000.00')
        print(f"  ✓ Payment settled: UGX {data['amount']} via cash")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        print("  ✓ Order marked paid")

        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'available')
        print("  ✓ Table 60 freed back to available")

        from payments.models import Payment
        payment = Payment.objects.latest('id')
        self.assertEqual(payment.received_by, self.cashier)
        self.assertIn(self.order, payment.orders.all())
        print("  ✓ Payment record correctly attributes cashier and order")

    def test_cannot_settle_unserved_orders(self):
        print("[Checkout] Blocks settling before kitchen/waiter finish")
        self.order.status = 'preparing'
        self.order.save()
        self.client.post('/checkout/login/', {'username': 'co_cashier', 'password': 'pass1234'})

        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {'method': 'cash', 'amount_tendered': '48000'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('served', r.json()['error'])
        print(f"  ✓ Correctly rejected: {r.json()['error']}")

        r = self.client.get('/checkout/')
        self.assertContains(r, 'Awaiting Service')
        self.assertContains(r, 'disabled')
        print("  ✓ Board shows 'Awaiting Service' and disables the Settle button")
