"""
Flutterwave Mobile Money (Uganda) integration.

Setup:
  1. Sign up at https://dashboard.flutterwave.com/signup
     Your account starts in TEST mode automatically — perfect for this.
  2. Settings -> API -> copy your Test Secret Key
  3. Put it in your .env as FLUTTERWAVE_SECRET_KEY=FLWSECK_TEST-xxxxxxxx

Until that key is set, every call here raises FlutterwaveNotConfigured so
the rest of the app can show a clear message instead of crashing.

Sandbox behavior worth knowing: Flutterwave auto-confirms Uganda mobile
money charges a few seconds after you initiate them in TEST mode — you
don't need a real phone to test the full pending -> successful flow.

Docs: https://developer.flutterwave.com/docs/collecting-payments/mobile-money/
      https://developer.flutterwave.com/docs/testing
"""
import uuid
import requests
from django.conf import settings

FLW_BASE_URL = 'https://api.flutterwave.com/v3'


class FlutterwaveError(Exception):
    """Raised when Flutterwave's API rejects the request or is unreachable."""


class FlutterwaveNotConfigured(FlutterwaveError):
    """Raised when no secret key has been set yet."""


def _headers():
    if not settings.FLUTTERWAVE_SECRET_KEY:
        raise FlutterwaveNotConfigured(
            "Mobile money isn't set up yet — add FLUTTERWAVE_SECRET_KEY to your .env file. "
            "Sign up free at https://dashboard.flutterwave.com/signup to get a test key."
        )
    return {
        'Authorization': f'Bearer {settings.FLUTTERWAVE_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def generate_tx_ref(payment_id):
    """A unique reference for this charge, so retries don't collide."""
    return f"rflow-{payment_id}-{uuid.uuid4().hex[:8]}"


def initiate_mobile_money_charge(*, phone_number, network, amount, email, tx_ref, fullname=''):
    """
    Starts a Mobile Money Uganda charge. The customer gets a USSD prompt on
    their phone to approve it (auto-approved after a few seconds in sandbox).

    Returns: {'tx_ref': str, 'flw_transaction_id': str, 'status': str}
    Raises: FlutterwaveError on any failure (network, bad request, rejected).
    """
    payload = {
        'tx_ref': tx_ref,
        'amount': str(amount),
        'currency': 'UGX',
        'email': email or 'customer@restaurantflow.local',
        'phone_number': phone_number,
        'network': network,  # 'MTN' or 'AIRTEL'
        'fullname': fullname or 'Walk-in customer',
    }
    try:
        response = requests.post(
            f'{FLW_BASE_URL}/charges?type=mobile_money_uganda',
            json=payload,
            headers=_headers(),
            timeout=15,
        )
    except requests.RequestException as e:
        raise FlutterwaveError(f"Could not reach Flutterwave: {e}")

    try:
        data = response.json()
    except ValueError:
        raise FlutterwaveError("Flutterwave returned an unreadable response.")

    if response.status_code >= 400 or data.get('status') != 'success':
        raise FlutterwaveError(data.get('message', 'Flutterwave rejected the charge.'))

    charge_data = data.get('data', {})
    return {
        'tx_ref': charge_data.get('tx_ref', tx_ref),
        'flw_transaction_id': str(charge_data.get('id', '')),
        'status': charge_data.get('status', 'pending'),
    }


def verify_transaction(flw_transaction_id):
    """
    Checks the real status of a previously-initiated charge.
    Returns one of: 'successful', 'failed', 'pending'.
    """
    if not flw_transaction_id:
        return 'pending'

    try:
        response = requests.get(
            f'{FLW_BASE_URL}/transactions/{flw_transaction_id}/verify',
            headers=_headers(),
            timeout=15,
        )
    except requests.RequestException as e:
        raise FlutterwaveError(f"Could not reach Flutterwave: {e}")

    try:
        data = response.json()
    except ValueError:
        raise FlutterwaveError("Flutterwave returned an unreadable response.")

    if response.status_code >= 400 or data.get('status') != 'success':
        raise FlutterwaveError(data.get('message', 'Could not verify the transaction.'))

    return data.get('data', {}).get('status', 'pending')
