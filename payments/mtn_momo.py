"""
MTN Mobile Money (MoMo) Open API — direct integration, no aggregator.

ONE-TIME SETUP (do this once, not on every request):
  You already have a Subscription Key from your MTN MoMo Developer
  dashboard (momodeveloper.mtn.com -> your subscription's Primary Key).
  That alone isn't enough — MTN also requires you to provision an
  "API User" + "API Key" using that subscription key, ONE TIME, before
  you can request access tokens. Run:

      python manage.py provision_mtn_momo

  It'll print MTN_MOMO_API_USER and MTN_MOMO_API_KEY — copy those into
  your .env alongside your subscription key. After that, this module
  handles token refresh automatically; you never touch this again.

SANDBOX QUIRK WORTH KNOWING: the sandbox ONLY accepts currency "EUR" —
real UGX amounts only work once MTN approves you for "Go-Live"
(production). MTN_MOMO_CURRENCY defaults to EUR for exactly this reason;
switch it to UGX yourself once you're live (confirm the exact production
currency code with MTN support during Go-Live — this can vary).

SANDBOX TEST NUMBERS (from MTN's official docs): any phone number you
use that ISN'T one of the special numbers below auto-succeeds after a
short delay — no real phone needed. To deliberately test a failure path,
use one of these as the payer's phone number:
    46733123450  -> payment fails
    46733123451  -> payment rejected by customer
    46733123452  -> payment expires (customer never responds)
    46733123455  -> payer not found
    46733123461  -> internal processing error
(Full list in MTN's Sandbox Use Case Testing Values table.)

Docs: https://momodeveloper.mtn.com/api-documentation
"""
import time
import base64
import re
import uuid
import requests
from django.conf import settings

SANDBOX_BASE_URL = "https://sandbox.momodeveloper.mtn.com"

# Cached in memory — a new access token is requested only when the old
# one is missing or about to expire, not on every single charge.
_token_cache = {'access_token': None, 'expires_at': 0}


class MTNMoMoError(Exception):
    """Raised when MTN's API rejects the request or is unreachable."""


class MTNMoMoNotConfigured(MTNMoMoError):
    """Raised when the subscription key / API user / API key aren't set yet."""


def _normalize_msisdn(phone_number):
    """
    MTN's API expects full international MSISDN format with no '+' and no
    leading 0 — e.g. '256772123456', not '0772123456' or '+256772123456'.
    A request with the wrong format is a common cause of a 400 here.
    """
    digits = re.sub(r'\D', '', phone_number)  # strip spaces, dashes, '+'
    if digits.startswith('0') and len(digits) == 10:
        return '256' + digits[1:]
    if digits.startswith('256'):
        return digits
    return digits  # already international, or malformed — let MTN's own validation catch the latter


def _base_url():
    # Sandbox and production use different base URLs in production —
    # MTN reveals the production URL during the Go-Live approval process.
    # Fill PRODUCTION_BASE_URL in your .env once MTN gives it to you.
    if settings.MTN_MOMO_ENV == 'production' and settings.MTN_MOMO_PRODUCTION_BASE_URL:
        return settings.MTN_MOMO_PRODUCTION_BASE_URL
    return SANDBOX_BASE_URL


def _require_config():
    if not all([settings.MTN_MOMO_SUBSCRIPTION_KEY, settings.MTN_MOMO_API_USER, settings.MTN_MOMO_API_KEY]):
        raise MTNMoMoNotConfigured(
            "MTN MoMo isn't fully set up yet. You need MTN_MOMO_SUBSCRIPTION_KEY (from your "
            "dashboard) plus MTN_MOMO_API_USER and MTN_MOMO_API_KEY (run "
            "'python manage.py provision_mtn_momo' once to generate these) in your .env."
        )


def _get_access_token():
    """Returns a cached Bearer token, refreshing it only when it's expired."""
    _require_config()

    if _token_cache['access_token'] and time.time() < _token_cache['expires_at']:
        return _token_cache['access_token']

    credentials = f"{settings.MTN_MOMO_API_USER}:{settings.MTN_MOMO_API_KEY}"
    encoded = base64.b64encode(credentials.encode()).decode()

    try:
        response = requests.post(
            f"{_base_url()}/collection/token/",
            headers={
                "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY,
                "Authorization": f"Basic {encoded}",
            },
            timeout=15,
        )
    except requests.RequestException as e:
        raise MTNMoMoError(f"Could not reach MTN MoMo: {e}")

    if response.status_code != 200:
        raise MTNMoMoError(f"MTN MoMo rejected the token request ({response.status_code}): {response.text[:200]}")

    data = response.json()
    _token_cache['access_token'] = data['access_token']
    # Refresh a little early (60s buffer) rather than right at the expiry second
    _token_cache['expires_at'] = time.time() + int(data.get('expires_in', 3600)) - 60
    return _token_cache['access_token']


def request_to_pay(*, phone_number, amount, reference_id=None, payer_message='RestaurantFlow payment'):
    """
    Sends a payment prompt to the customer's phone. MTN's API is async by
    design — this call returns 202 Accepted immediately with no body; the
    real outcome only comes from check_transaction_status() afterward.

    IMPORTANT: MTN's X-Reference-Id MUST be a genuine UUIDv4 — sending
    anything else (e.g. a friendly string like 'rflow-5') gets the whole
    request rejected with a 400. So this function ALWAYS generates its
    own UUID4 for the actual MTN request, ignoring whatever string the
    caller passes in as `reference_id` — that parameter is accepted only
    for logging/compatibility with the other provider modules, never sent
    to MTN. The real UUID4 used is what's returned, and THAT is what you
    must store and pass to check_transaction_status() later.

    Returns: {'reference_id': str, 'status': 'PENDING'}  <- reference_id here IS a real UUID4
    Raises: MTNMoMoError on failure.
    """
    _require_config()
    token = _get_access_token()
    mtn_reference_id = str(uuid.uuid4())  # MUST be a real UUID4 — ignore whatever the caller passed in
    normalized_phone = _normalize_msisdn(phone_number)

    payload = {
        "amount": str(amount),
        "currency": settings.MTN_MOMO_CURRENCY,
        "externalId": mtn_reference_id,
        "payer": {"partyIdType": "MSISDN", "partyId": normalized_phone},
        "payerMessage": payer_message,
        "payeeNote": payer_message,
    }

    try:
        response = requests.post(
            f"{_base_url()}/collection/v1_0/requesttopay",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Reference-Id": mtn_reference_id,
                "X-Target-Environment": settings.MTN_MOMO_ENV,
                "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
    except requests.RequestException as e:
        raise MTNMoMoError(f"Could not reach MTN MoMo: {e}")

    if response.status_code != 202:
        raise MTNMoMoError(f"MTN MoMo rejected the charge ({response.status_code}): {response.text[:200]}")

    return {'reference_id': mtn_reference_id, 'status': 'PENDING'}


def check_transaction_status(reference_id):
    """
    Polls for the real outcome of a previously-initiated charge.
    Returns one of: 'SUCCESSFUL', 'FAILED', 'PENDING'.
    """
    _require_config()
    token = _get_access_token()

    try:
        response = requests.get(
            f"{_base_url()}/collection/v1_0/requesttopay/{reference_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Target-Environment": settings.MTN_MOMO_ENV,
                "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        raise MTNMoMoError(f"Could not reach MTN MoMo: {e}")

    if response.status_code != 200:
        raise MTNMoMoError(f"Could not check transaction status ({response.status_code}): {response.text[:200]}")

    return response.json().get('status', 'PENDING').upper()
