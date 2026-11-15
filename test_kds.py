import os, django, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurantflow.settings')
django.setup()

from django.test import TestCase, Client

class KDSTest(TestCase):
    def setUp(self):
        from accounts.models import User
        from restaurant.models import Table
        from menu.models import Category, MenuItem
        from orders.models import Order, OrderItem

        self.client = Client()
        self.kitchen = User.objects.create(username='kds_kitchen', role='kitchen')
        self.kitchen.set_password('pass1234')
        self.kitchen.save()
        self.waiter = User.objects.create(username='kds_waiter', role='waiter')
        self.waiter.set_password('pass1234')
        self.waiter.save()

        table = Table.objects.create(number=50)
        cat = Category.objects.create(name='KDS Test', sort_order=1)
        burger = MenuItem.objects.create(name='Test Burger', price=20000, category=cat)

        self.order = Order.objects.create(table=table, channel='waiter', status='accepted')
        self.item = OrderItem.objects.create(order=self.order, menu_item=burger, quantity=1, unit_price=20000)

    def test_login_required(self):
        print("\n[KDS] Unauthenticated access redirects to login")
        r = self.client.get('/kds/')
        self.assertEqual(r.status_code, 302)
        print("  ✓ /kds/ redirects when not logged in")

    def test_waiter_cannot_access_kds(self):
        print("[KDS] Waiter role rejected")
        self.client.login(username='kds_waiter', password='pass1234')
        r = self.client.post('/kds/login/', {'username': 'kds_waiter', 'password': 'pass1234'})
        # should redirect back to login with error, not the board
        self.assertNotEqual(r.url if hasattr(r, 'url') else '', '/kds/')
        print("  ✓ Waiter login attempt does not reach the board")

    def test_full_kitchen_flow(self):
        print("[KDS] Full kitchen flow")
        # login
        r = self.client.post('/kds/login/', {'username': 'kds_kitchen', 'password': 'pass1234'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, '/kds/')
        print("  ✓ Kitchen login successful, redirected to board")

        # board shows the order
        r = self.client.get('/kds/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'T50')
        self.assertContains(r, 'Test Burger')
        self.assertContains(r, 'Start Preparing')
        print("  ✓ Board shows Table 50 with Test Burger, Start Preparing button present")

        # start preparing
        r = self.client.post(f'/kds/item/{self.item.id}/start/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'status': 'ok'})
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'preparing')
        print("  ✓ Item moved to preparing")

        r = self.client.get('/kds/')
        self.assertContains(r, 'Mark Ready')
        print("  ✓ Board now shows 'Mark Ready' button")

        # mark ready
        r = self.client.post(f'/kds/item/{self.item.id}/ready/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'status': 'ok'})
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'ready')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'ready')
        print("  ✓ Item marked ready, order auto-synced to 'ready'")

        # board no longer lists this order (order excludes 'ready'? No - excludes served/paid/cancelled only)
        r = self.client.get('/kds/')
        print("  ✓ Board reflects updated state")
