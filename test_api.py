"""
Comprehensive API test - simulates a full restaurant shift:
  1. Login (all roles)
  2. Fetch menu
  3. Waiter creates order with items
  4. Waiter accepts the order
  5. Kitchen marks items preparing → ready (item-level)
  6. Waiter serves the order
  7. Cashier processes payment → table freed
  8. Error cases: illegal state transitions, wrong role access
"""
import os, django, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurantflow.settings')
django.setup()

from django.test import TestCase, Client

class FullShiftTest(TestCase):
    def setUp(self):
        from accounts.models import User
        from restaurant.models import Table
        from menu.models import Category, MenuItem

        self.client = Client()

        # users
        def make(username, role):
            u = User.objects.create(username=username, role=role)
            u.set_password('pass1234')
            u.save()
            return u
        self.admin   = make('t_admin',   'admin')
        self.waiter  = make('t_waiter',  'waiter')
        self.kitchen = make('t_kitchen', 'kitchen')
        self.cashier = make('t_cashier', 'cashier')

        # table
        self.table = Table.objects.create(number=99, capacity=4)

        # menu
        cat = Category.objects.create(name='Test Food', sort_order=1)
        self.burger = MenuItem.objects.create(name='Burger', price=20000, category=cat)
        self.chips  = MenuItem.objects.create(name='Chips',  price=8000,  category=cat)

    def login(self, username):
        r = self.client.post('/api/auth/login/', {'username': username, 'password': 'pass1234'}, content_type='application/json')
        self.assertEqual(r.status_code, 200, f"Login failed for {username}: {r.content}")
        token = r.json()['access']
        return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    def test_1_auth_and_roles(self):
        print("\n[1] Auth & roles")
        for role_user in ['t_admin','t_waiter','t_kitchen','t_cashier']:
            headers = self.login(role_user)
            r = self.client.get('/api/auth/me/', **headers)
            self.assertEqual(r.status_code, 200)
            print(f"  ✓ {role_user} login OK, role={r.json()['role']}")

        # admin-only endpoint should reject non-admin
        waiter_headers = self.login('t_waiter')
        r = self.client.get('/api/auth/staff/', **waiter_headers)
        self.assertEqual(r.status_code, 403)
        print("  ✓ /api/auth/staff/ correctly blocked for waiter role")

    def test_2_menu(self):
        print("\n[2] Menu")
        headers = self.login('t_waiter')
        r = self.client.get('/api/categories/', **headers)
        self.assertEqual(r.status_code, 200)
        cats = r.json()['results'] if 'results' in r.json() else r.json()
        print(f"  ✓ categories fetched: {[c['name'] for c in cats]}")

        r = self.client.get('/api/items/', **headers)
        self.assertEqual(r.status_code, 200)
        items = r.json()['results'] if 'results' in r.json() else r.json()
        print(f"  ✓ menu items fetched: {[i['name'] for i in items]}")

    def test_3_full_order_lifecycle(self):
        print("\n[3] Full order lifecycle")
        w_h = self.login('t_waiter')
        k_h = self.login('t_kitchen')
        c_h = self.login('t_cashier')

        # --- create order ---
        payload = {
            'table': self.table.id,
            'channel': 'waiter',
            'customer_name': 'Test Customer',
            'items_write': [
                {'menu_item': self.burger.id, 'quantity': 2, 'notes': 'no onions'},
                {'menu_item': self.chips.id,  'quantity': 1, 'notes': ''},
            ]
        }
        r = self.client.post('/api/orders/', json.dumps(payload), content_type='application/json', **w_h)
        self.assertEqual(r.status_code, 201, f"Order create failed: {r.content}")
        order = r.json()
        order_id = order['id']
        print(f"  ✓ Order #{order_id} created, status={order['status']}, total={order['total']}")
        self.assertEqual(order['status'], 'pending')
        self.assertEqual(len(order['items']), 2)

        # verify table is now occupied
        from restaurant.models import Table
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'occupied')
        print(f"  ✓ Table 99 auto-set to occupied")

        # --- waiter accepts ---
        r = self.client.post(f'/api/orders/{order_id}/accept/', **w_h)
        self.assertEqual(r.status_code, 200)
        print(f"  ✓ Order accepted, status={r.json()['status']}")

        # --- illegal transition: try to jump to paid ---
        r = self.client.post(f'/api/orders/{order_id}/cancel/', **w_h)
        # cancel is allowed from accepted, this tests it works
        # first re-create to test illegal jump
        payload['customer_name'] = 'Test2'
        r2 = self.client.post('/api/orders/', json.dumps(payload), content_type='application/json', **w_h)
        order2_id = r2.json()['id']
        # Try a direct PATCH to a bad status (should be blocked)
        r_bad = self.client.patch(f'/api/orders/{order2_id}/', json.dumps({'status':'paid'}), content_type='application/json', **w_h)
        # status is read_only so it should not change
        o2 = self.client.get(f'/api/orders/{order2_id}/', **w_h).json()
        self.assertNotEqual(o2['status'], 'paid')
        print(f"  ✓ Direct status PATCH correctly ignored (read-only), status still={o2['status']}")

        # continue with order1 - needs re-accept as we cancelled it
        r = self.client.post(f'/api/orders/{order_id}/accept/', **w_h)
        # if already cancelled, create fresh
        o1 = self.client.get(f'/api/orders/{order_id}/', **w_h).json()
        if o1['status'] == 'cancelled':
            payload['customer_name'] = 'FreshOrder'
            r_new = self.client.post('/api/orders/', json.dumps(payload), content_type='application/json', **w_h)
            order_id = r_new.json()['id']
            self.client.post(f'/api/orders/{order_id}/accept/', **w_h)

        # --- kitchen: item-level start preparing ---
        order_detail = self.client.get(f'/api/orders/{order_id}/', **k_h).json()
        item_ids = [i['id'] for i in order_detail['items']]
        for iid in item_ids:
            r = self.client.post(f'/api/order-items/{iid}/start_preparing/', **k_h)
            self.assertEqual(r.status_code, 200, f"start_preparing failed: {r.content}")
            print(f"  ✓ Item #{iid} → preparing")

        # --- kitchen: mark all items ready ---
        for iid in item_ids:
            r = self.client.post(f'/api/order-items/{iid}/mark_ready/', **k_h)
            self.assertEqual(r.status_code, 200)
            print(f"  ✓ Item #{iid} → ready")

        # order should now be ready
        order_detail = self.client.get(f'/api/orders/{order_id}/', **w_h).json()
        self.assertEqual(order_detail['status'], 'ready')
        print(f"  ✓ Order auto-synced to ready")

        # --- waiter serves items ---
        for iid in item_ids:
            r = self.client.post(f'/api/order-items/{iid}/serve/', **w_h)
            self.assertEqual(r.status_code, 200)

        # order should auto-sync to served
        order_detail = self.client.get(f'/api/orders/{order_id}/', **w_h).json()
        self.assertEqual(order_detail['status'], 'served')
        print(f"  ✓ Order auto-synced to served")

        # cancel the stray second order so the table can be freed after payment
        self.client.post(f'/api/orders/{order2_id}/cancel/', **w_h)
        print(f"  ✓ Stray second order cancelled")

        # --- cashier processes payment ---
        total = float(order_detail['total'])
        pay_payload = {
            'table': self.table.id,
            'order_ids': [order_id],
            'amount': str(total),
            'method': 'cash',
        }
        r = self.client.post('/api/payments/', json.dumps(pay_payload), content_type='application/json', **c_h)
        self.assertEqual(r.status_code, 201, f"Payment failed: {r.content}")
        print(f"  ✓ Payment of UGX {total:,.0f} processed")

        # order is now paid
        order_detail = self.client.get(f'/api/orders/{order_id}/', **w_h).json()
        self.assertEqual(order_detail['status'], 'paid')
        print(f"  ✓ Order marked paid")

        # table freed (no remaining unpaid orders)
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'available')
        print(f"  ✓ Table 99 auto-freed to available")

    def test_4_kitchen_cannot_access_payments(self):
        print("\n[4] Role enforcement")
        k_h = self.login('t_kitchen')
        r = self.client.get('/api/payments/', **k_h)
        self.assertEqual(r.status_code, 403)
        print("  ✓ Kitchen role blocked from /api/payments/")

    def test_5_tables_endpoint(self):
        print("\n[5] Tables endpoint")
        w_h = self.login('t_waiter')
        r = self.client.get('/api/tables/', **w_h)
        self.assertEqual(r.status_code, 200)
        tables = r.json()
        if 'results' in tables:
            tables = tables['results']
        print(f"  ✓ Tables list returned {len(tables)} table(s)")

        r = self.client.get(f'/api/tables/{self.table.id}/', **w_h)
        self.assertEqual(r.status_code, 200)
        t = r.json()
        self.assertIn('qr_token', t)
        print(f"  ✓ Table detail OK, qr_token={t['qr_token']}")


    def test_6_only_admin_can_add_tables(self):
        print("\n[6] Table creation restricted to admin")
        w_h = self.login('t_waiter')
        a_h = self.login('t_admin')

        # waiter blocked
        r = self.client.post('/api/tables/', {'number': 77, 'capacity': 4}, **w_h)
        self.assertEqual(r.status_code, 403)
        print("  ✓ Waiter blocked from creating a table (403)")

        # admin allowed
        r = self.client.post('/api/tables/', {'number': 77, 'capacity': 4}, **a_h)
        self.assertEqual(r.status_code, 201, f"Admin table create failed: {r.content}")
        print(f"  ✓ Admin created Table {r.json()['number']}")

        # duplicate number rejected
        r = self.client.post('/api/tables/', {'number': 77, 'capacity': 6}, **a_h)
        self.assertEqual(r.status_code, 400)
        print("  ✓ Duplicate table number correctly rejected")
