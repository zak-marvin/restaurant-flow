"""
Tests the cash calculator and mobile money flow.

Note: this sandbox has no network access to api.flutterwave.com, so every
Flutterwave call is mocked here. This verifies all the business logic
(state machine, double-charge guard, change calculation) works correctly.
Once you have real sandbox keys, test the actual HTTP calls yourself —
Flutterwave auto-confirms mobile money charges in TEST mode after a few
seconds, no real phone needed.
"""
import os, django
from unittest.mock import patch
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurantflow.settings')
django.setup()

from django.test import TestCase, Client


class CashCalculatorTest(TestCase):
    def setUp(self):
        from accounts.models import User
        from restaurant.models import Table
        from menu.models import Category, MenuItem
        from orders.models import Order, OrderItem

        self.client = Client()
        self.cashier = User.objects.create(username='cash_cashier', role='cashier')
        self.cashier.set_password('pass1234')
        self.cashier.save()

        self.table = Table.objects.create(number=70, capacity=4)
        self.table.status = 'occupied'
        self.table.save()

        cat = Category.objects.create(name='Cash Test', sort_order=1)
        burger = MenuItem.objects.create(name='Cash Burger', price=15000, category=cat)

        self.order = Order.objects.create(table=self.table, channel='waiter', status='served')
        OrderItem.objects.create(order=self.order, menu_item=burger, quantity=2, unit_price=15000, status='served')
        # total = 30000

        self.client.post('/checkout/login/', {'username': 'cash_cashier', 'password': 'pass1234'})

    def test_change_calculated_correctly(self):
        print("\n[Cash] Correct change calculation")
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'cash', 'amount_tendered': '50000',
        })
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['change_given'], '20000.00')
        print(f"  ✓ Tendered 50000 for a 30000 bill -> change 20000")

        from payments.models import Payment
        payment = Payment.objects.get(id=data['payment_id'])
        self.assertEqual(payment.amount_tendered, 50000)
        self.assertEqual(payment.change_given, 20000)
        self.assertEqual(payment.status, 'successful')
        print("  ✓ Payment record stores tendered amount and change correctly")

    def test_insufficient_cash_rejected(self):
        print("[Cash] Insufficient amount rejected")
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'cash', 'amount_tendered': '10000',
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('less than the total', r.json()['error'])
        print(f"  ✓ Correctly rejected: {r.json()['error']}")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'served')
        print("  ✓ Order remains unpaid — no partial settlement happened")

    def test_exact_change_is_zero(self):
        print("[Cash] Exact amount gives zero change")
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'cash', 'amount_tendered': '30000',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['change_given'], '0.00')
        print("  ✓ Exact payment correctly shows zero change")


class MobileMoneyTest(TestCase):
    def setUp(self):
        from accounts.models import User
        from restaurant.models import Table
        from menu.models import Category, MenuItem
        from orders.models import Order, OrderItem

        self.client = Client()
        self.cashier = User.objects.create(username='momo_cashier', role='cashier')
        self.cashier.set_password('pass1234')
        self.cashier.save()

        self.table = Table.objects.create(number=71, capacity=4)
        self.table.status = 'occupied'
        self.table.save()

        cat = Category.objects.create(name='Momo Test', sort_order=1)
        item = MenuItem.objects.create(name='Momo Pizza', price=25000, category=cat)

        self.order = Order.objects.create(table=self.table, channel='waiter', status='served')
        OrderItem.objects.create(order=self.order, menu_item=item, quantity=1, unit_price=25000, status='served')
        # total = 25000

        self.client.post('/checkout/login/', {'username': 'momo_cashier', 'password': 'pass1234'})

    def test_missing_credentials_gives_clear_error(self):
        print("\n[MobileMoney] Clear error when Yo! Payments isn't configured yet")
        # No YO_PAYMENTS_API_USERNAME/PASSWORD set in this test environment — should fail gracefully
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772123456',
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('YO_PAYMENTS_API_USERNAME', r.json()['error'])
        print(f"  ✓ Clear setup message returned: {r.json()['error'][:60]}...")

        from payments.models import Payment
        payment = Payment.objects.latest('id')
        self.assertEqual(payment.status, 'failed')
        print("  ✓ Payment correctly marked failed, not stuck pending forever")

    @patch('payments.yo_payments.initiate_mobile_money_charge')
    def test_successful_charge_stays_pending_until_verified(self, mock_initiate):
        print("[MobileMoney] Charge initiated -> stays pending, doesn't pay early")
        mock_initiate.return_value = {'transaction_reference': '999888', 'status': 'PENDING'}
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772123456',
        })
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['status'], 'pending')
        print(f"  ✓ Charge initiated, payment_id={data['payment_id']}")

        # Order must NOT be marked paid yet — customer hasn't approved on their phone
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'served')
        print("  ✓ Order correctly still 'served', not prematurely marked paid")

        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'occupied')
        print("  ✓ Table correctly still occupied while payment is pending")

    @patch('payments.yo_payments.check_transaction_status')
    @patch('payments.yo_payments.initiate_mobile_money_charge')
    def test_polling_finalizes_on_success(self, mock_initiate, mock_check_status):
        print("[MobileMoney] Polling confirms success -> order paid, table freed")
        mock_initiate.return_value = {'transaction_reference': '777666', 'status': 'PENDING'}
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772999888',
        })
        payment_id = r.json()['payment_id']

        # Simulate customer approving on their phone — check_transaction_status now returns SUCCEEDED
        mock_check_status.return_value = 'SUCCEEDED'
        r2 = self.client.get(f'/checkout/payment/{payment_id}/status/')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()['status'], 'successful')
        print("  ✓ Status poll reports 'successful' after customer approval")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        print("  ✓ Order now marked paid")

        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'available')
        print("  ✓ Table freed back to available")

    @patch('payments.yo_payments.check_transaction_status')
    @patch('payments.yo_payments.initiate_mobile_money_charge')
    def test_polling_handles_decline(self, mock_initiate, mock_check_status):
        print("[MobileMoney] Customer declines -> payment fails, order stays unpaid")
        mock_initiate.return_value = {'transaction_reference': '111222', 'status': 'PENDING'}
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772111222',
        })
        payment_id = r.json()['payment_id']

        mock_check_status.return_value = 'FAILED'
        r2 = self.client.get(f'/checkout/payment/{payment_id}/status/')
        self.assertEqual(r2.json()['status'], 'failed')
        print("  ✓ Status poll reports 'failed' after customer declines")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'served')
        print("  ✓ Order correctly remains unpaid — cashier can retry with another method")

    @patch('payments.yo_payments.initiate_mobile_money_charge')
    def test_cannot_double_charge_while_pending(self, mock_initiate):
        print("[MobileMoney] Blocks a second charge while one is already pending")
        mock_initiate.return_value = {'transaction_reference': '333444', 'status': 'PENDING'}
        r1 = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772333444',
        })
        self.assertEqual(r1.json()['status'], 'pending')

        r2 = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772333444',
        })
        self.assertEqual(r2.status_code, 400)
        self.assertIn('already in progress', r2.json()['error'])
        print(f"  ✓ Correctly blocked: {r2.json()['error']}")


class MTNDirectTest(TestCase):
    """
    Tests the 'direct' provider mode routing to MTN MoMo. Since this
    sandbox has no network access to momodeveloper.mtn.com, every MTN
    call is mocked — this verifies the dispatcher routes correctly and
    the same state machine (pending -> paid/failed) holds regardless of
    which provider is configured.
    """
    def setUp(self):
        from accounts.models import User
        from restaurant.models import Table
        from menu.models import Category, MenuItem
        from orders.models import Order, OrderItem
        from django.test import override_settings

        self.override = override_settings(MOBILE_MONEY_PROVIDER='direct')
        self.override.enable()

        self.client = Client()
        self.cashier = User.objects.create(username='mtn_cashier', role='cashier')
        self.cashier.set_password('pass1234')
        self.cashier.save()

        self.table = Table.objects.create(number=80, capacity=4)
        self.table.status = 'occupied'
        self.table.save()

        cat = Category.objects.create(name='MTN Test', sort_order=1)
        item = MenuItem.objects.create(name='MTN Chicken', price=22000, category=cat)

        self.order = Order.objects.create(table=self.table, channel='waiter', status='served')
        OrderItem.objects.create(order=self.order, menu_item=item, quantity=1, unit_price=22000, status='served')

        self.client.post('/checkout/login/', {'username': 'mtn_cashier', 'password': 'pass1234'})

    def tearDown(self):
        self.override.disable()

    def test_network_required_in_direct_mode(self):
        print("\n[MTN Direct] Network selection required")
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772555666',
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('Select MTN or Airtel', r.json()['error'])
        print(f"  ✓ Correctly rejected without a network: {r.json()['error']}")

    def test_airtel_gives_clear_not_built_message(self):
        print("[MTN Direct] Airtel correctly reports not-yet-built")
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772555666', 'network': 'AIRTEL',
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('Airtel', r.json()['error'])
        self.assertIn('developers.airtel.africa', r.json()['error'])
        print(f"  ✓ Clear message: {r.json()['error'][:70]}...")

    @patch('payments.mtn_momo.request_to_pay')
    def test_mtn_charge_stays_pending(self, mock_request_to_pay):
        print("[MTN Direct] Charge initiated -> stays pending")
        mock_request_to_pay.return_value = {'reference_id': 'rflow-1', 'status': 'PENDING'}
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772555666', 'network': 'MTN',
        })
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['status'], 'pending')
        print(f"  ✓ MTN charge initiated, payment_id={r.json()['payment_id']}")

        from payments.models import Payment
        payment = Payment.objects.get(id=r.json()['payment_id'])
        self.assertEqual(payment.network, 'MTN')
        self.assertEqual(payment.provider, 'direct')
        print("  ✓ Payment correctly records network='MTN' and provider='direct'")

    @patch('payments.mtn_momo.check_transaction_status')
    @patch('payments.mtn_momo.request_to_pay')
    def test_mtn_polling_finalizes_on_success(self, mock_request_to_pay, mock_check_status):
        print("[MTN Direct] Polling confirms success -> order paid, table freed")
        mock_request_to_pay.return_value = {'reference_id': 'rflow-2', 'status': 'PENDING'}
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772555666', 'network': 'MTN',
        })
        payment_id = r.json()['payment_id']

        mock_check_status.return_value = 'SUCCESSFUL'
        r2 = self.client.get(f'/checkout/payment/{payment_id}/status/')
        self.assertEqual(r2.json()['status'], 'successful')
        print("  ✓ Status poll reports 'successful'")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        self.table.refresh_from_db()
        self.assertEqual(self.table.status, 'available')
        print("  ✓ Order paid, table freed")

    @patch('payments.mtn_momo.request_to_pay')
    def test_mtn_not_configured_gives_clear_error(self, mock_request_to_pay):
        print("[MTN Direct] Clear error when MTN credentials aren't set")
        from payments.mtn_momo import MTNMoMoNotConfigured
        mock_request_to_pay.side_effect = MTNMoMoNotConfigured(
            "MTN MoMo isn't fully set up yet. You need MTN_MOMO_SUBSCRIPTION_KEY..."
        )
        r = self.client.post(f'/checkout/table/{self.table.id}/settle/', {
            'method': 'mobile_money', 'phone_number': '0772555666', 'network': 'MTN',
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('MTN_MOMO_SUBSCRIPTION_KEY', r.json()['error'])
        print(f"  ✓ Clear setup message: {r.json()['error'][:60]}...")


class MTNRequestFormatTest(TestCase):
    """
    Directly tests payments/mtn_momo.py's request formatting — the actual
    bug that caused a real 400 from MTN: a friendly reference string like
    'rflow-5' was being sent as X-Reference-Id, which MTN requires to be a
    genuine UUIDv4. Also verifies phone number normalization.
    """
    def setUp(self):
        from django.test import override_settings
        self.override = override_settings(
            MTN_MOMO_SUBSCRIPTION_KEY='test-sub-key',
            MTN_MOMO_API_USER='test-user',
            MTN_MOMO_API_KEY='test-key',
        )
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    @patch('payments.mtn_momo.requests.post')
    @patch('payments.mtn_momo._get_access_token')
    def test_x_reference_id_is_real_uuid_not_friendly_string(self, mock_token, mock_post):
        import uuid as uuid_lib
        from payments import mtn_momo

        print("\n[MTN Format] X-Reference-Id is a real UUIDv4")
        mock_token.return_value = 'fake-token'
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = ''

        # Pass a non-UUID friendly reference, like checkout/views.py does
        result = mtn_momo.request_to_pay(
            phone_number='0772123456', amount=1000, reference_id='rflow-5',
        )

        # Check what was actually sent to MTN
        call_headers = mock_post.call_args.kwargs['headers']
        sent_reference = call_headers['X-Reference-Id']

        # Must be a valid UUID4 — this would have raised ValueError before the fix
        parsed = uuid_lib.UUID(sent_reference, version=4)
        self.assertEqual(str(parsed), sent_reference)
        print(f"  ✓ X-Reference-Id sent to MTN is a valid UUID4: {sent_reference}")

        self.assertNotEqual(sent_reference, 'rflow-5')
        print("  ✓ The friendly 'rflow-5' string was correctly NOT sent as the reference")

        # The function's return value must match what was actually sent,
        # since that's what gets polled later
        self.assertEqual(result['reference_id'], sent_reference)
        print("  ✓ Returned reference_id matches what was actually sent to MTN")

    @patch('payments.mtn_momo.requests.post')
    @patch('payments.mtn_momo._get_access_token')
    def test_local_phone_format_normalized_to_international(self, mock_token, mock_post):
        from payments import mtn_momo

        print("[MTN Format] Local phone format normalized for MTN")
        mock_token.return_value = 'fake-token'
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = ''

        mtn_momo.request_to_pay(phone_number='0772123456', amount=1000)

        sent_body = mock_post.call_args.kwargs['json']
        sent_phone = sent_body['payer']['partyId']
        self.assertEqual(sent_phone, '256772123456')
        print(f"  ✓ '0772123456' correctly normalized to '{sent_phone}'")

    @patch('payments.mtn_momo.requests.post')
    @patch('payments.mtn_momo._get_access_token')
    def test_already_international_format_untouched(self, mock_token, mock_post):
        from payments import mtn_momo

        print("[MTN Format] Already-international format passes through unchanged")
        mock_token.return_value = 'fake-token'
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = ''

        mtn_momo.request_to_pay(phone_number='256772123456', amount=1000)

        sent_body = mock_post.call_args.kwargs['json']
        self.assertEqual(sent_body['payer']['partyId'], '256772123456')
        print("  ✓ '256772123456' passed through unchanged, as expected")
