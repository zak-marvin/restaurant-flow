"""
Regression tests for permission, notification and webhook fixes.
Run: python manage.py test test_security
"""
import os, json, django
from unittest.mock import patch
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurantflow.settings')
django.setup()

from django.test import TestCase, Client, override_settings


class SecurityFixesTest(TestCase):
    def setUp(self):
        from accounts.models import User
        from restaurant.models import Table
        from menu.models import Category, MenuItem
        self.c = Client()
        for name, role in [('w', 'waiter'), ('k', 'kitchen'), ('c', 'cashier')]:
            u = User.objects.create(username=name, role=role)
            u.set_password('x'); u.save()
        self.table = Table.objects.create(number=1)
        cat = Category.objects.create(name='Food')
        self.item = MenuItem.objects.create(category=cat, name='Rolex', price=5000)

    def h(self, username):
        r = self.c.post('/api/auth/login/', json.dumps({'username': username, 'password': 'x'}),
                        content_type='application/json')
        return {'HTTP_AUTHORIZATION': 'Bearer ' + r.json()['access']}

    def place_order(self, headers):
        body = {'table': self.table.id, 'items_write': [{'menu_item': self.item.id, 'quantity': 1}]}
        return self.c.post('/api/orders/', json.dumps(body), content_type='application/json', **headers)

    # --- order accept / cancel ---
    def test_only_waiter_or_admin_can_accept_and_cancel(self):
        order = self.place_order(self.h('w')).json()
        oid = order['id']
        self.assertEqual(self.c.post(f'/api/orders/{oid}/accept/', **self.h('k')).status_code, 403)
        self.assertEqual(self.c.post(f'/api/orders/{oid}/cancel/', **self.h('c')).status_code, 403)
        self.assertEqual(self.c.post(f'/api/orders/{oid}/accept/', **self.h('w')).status_code, 200)

    # --- order items ---
    def test_order_items_cannot_be_edited_or_created_directly(self):
        order = self.place_order(self.h('w')).json()
        iid = order['items'][0]['id']
        c_h = self.h('c')
        r = self.c.patch(f'/api/order-items/{iid}/', json.dumps({'status': 'served'}),
                         content_type='application/json', **c_h)
        self.assertEqual(r.status_code, 405)
        self.assertEqual(self.c.delete(f'/api/order-items/{iid}/', **c_h).status_code, 405)
        self.assertEqual(self.c.get(f'/api/order-items/{iid}/', **c_h).json()['status'], 'pending')

    # --- payments ---
    def test_payments_cannot_be_edited_or_deleted(self):
        c_h = self.h('c')
        self.assertEqual(self.c.delete('/api/payments/1/', **c_h).status_code, 405)
        self.assertEqual(self.c.patch('/api/payments/1/', '{}', content_type='application/json', **c_h).status_code, 405)

    def test_mobile_money_rejected_on_rest_endpoint(self):
        from orders.models import Order
        o = Order.objects.create(table=self.table, status='served')
        from orders.models import OrderItem
        OrderItem.objects.create(order=o, menu_item=self.item, quantity=1, unit_price=5000, status='served')
        body = {'table': self.table.id, 'order_ids': [o.id], 'amount': '5000.00', 'method': 'mobile_money'}
        r = self.c.post('/api/payments/', json.dumps(body), content_type='application/json', **self.h('c'))
        self.assertEqual(r.status_code, 400)
        o.refresh_from_db()
        self.assertEqual(o.status, 'served')  # not marked paid

    # --- notifications must never break ordering ---
    def test_push_failure_does_not_break_order_creation(self):
        from accounts.models import User
        from notifications.models import DeviceToken
        DeviceToken.objects.create(user=User.objects.get(username='k'), token='tok-1')
        with patch('notifications.services.FCM_AVAILABLE', True), \
             patch('notifications.services.messaging', create=True) as m, \
             self.assertLogs('notifications.services', level='ERROR'):
            m.send_each_for_multicast.side_effect = RuntimeError('fcm down')
            r = self.place_order(self.h('w'))
        self.assertEqual(r.status_code, 201)

    # --- Flutterwave webhook resolves by rflow-<id> reference ---
    @override_settings(FLUTTERWAVE_WEBHOOK_HASH='secret')
    def test_flutterwave_webhook_marks_payment_paid(self):
        from orders.models import Order, OrderItem
        from payments.models import Payment
        o = Order.objects.create(table=self.table, status='served')
        OrderItem.objects.create(order=o, menu_item=self.item, quantity=1, unit_price=5000, status='served')
        p = Payment.objects.create(table=self.table, amount=5000, method='mobile_money',
                                   status='pending', provider='flutterwave')
        p.orders.set([o])
        body = {'data': {'tx_ref': f'rflow-{p.id}', 'status': 'successful'}}
        r = self.c.post('/checkout/webhook/flutterwave/', json.dumps(body),
                        content_type='application/json', HTTP_VERIF_HASH='secret')
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db(); o.refresh_from_db()
        self.assertEqual((p.status, o.status), ('successful', 'paid'))
