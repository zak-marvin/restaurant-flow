"""
Single entry point the rest of the app calls for mobile money — it doesn't
know or care which provider is behind it. Switch providers by changing
MOBILE_MONEY_PROVIDER in your .env, nothing else needs to change:

  MOBILE_MONEY_PROVIDER=yo_payments   (default — aggregator, network-agnostic)
  MOBILE_MONEY_PROVIDER=flutterwave   (aggregator, built+tested, currently waitlisted)
  MOBILE_MONEY_PROVIDER=direct        (straight to MTN/Airtel, no aggregator —
                                        requires a 'network' of 'MTN' or 'AIRTEL'
                                        on every charge, since each network is a
                                        separate integration with its own credentials)

initiate_charge(phone_number, amount, reference, network=None) -> {'provider_id', 'status'}
check_status(provider_id, network=None) -> 'successful' | 'failed' | 'pending'

Important: the provider lookup happens INSIDE each function call, every
time — not once at import time. That matters for tests using
override_settings, and it also means changing MOBILE_MONEY_PROVIDER never
requires touching code, just the .env + a server restart.
"""
from django.conf import settings


class ProviderError(Exception):
    """Raised when the configured provider rejects a charge or is unreachable."""


class ProviderNotConfigured(ProviderError):
    """Raised when the configured provider's credentials aren't set up yet."""


_YO_STATUS_MAP = {
    'SUCCEEDED': 'successful', 'FAILED': 'failed',
    'PENDING': 'pending', 'INDETERMINATE': 'pending',
}
_MTN_STATUS_MAP = {'SUCCESSFUL': 'successful', 'FAILED': 'failed', 'PENDING': 'pending'}


def initiate_charge(*, phone_number, amount, reference, network=None, email=None):
    provider = settings.MOBILE_MONEY_PROVIDER

    if provider == 'flutterwave':
        from . import flutterwave as flw
        try:
            result = flw.initiate_mobile_money_charge(
                phone_number=phone_number, network=network or 'MTN', amount=amount,
                email=email, tx_ref=reference,
            )
        except flw.FlutterwaveNotConfigured as e:
            raise ProviderNotConfigured(str(e)) from e
        except flw.FlutterwaveError as e:
            raise ProviderError(str(e)) from e
        return {'provider_id': result['flw_transaction_id'], 'status': result['status']}

    elif provider == 'direct':
        network = (network or '').upper()
        if network == 'MTN':
            from . import mtn_momo as mtn
            try:
                result = mtn.request_to_pay(phone_number=phone_number, amount=amount, reference_id=reference)
            except mtn.MTNMoMoNotConfigured as e:
                raise ProviderNotConfigured(str(e)) from e
            except mtn.MTNMoMoError as e:
                raise ProviderError(str(e)) from e
            return {'provider_id': result['reference_id'], 'status': 'pending'}
        elif network == 'AIRTEL':
            raise ProviderNotConfigured(
                "Airtel direct integration isn't built yet — sign up at "
                "https://developers.airtel.africa, and once you have sandbox keys "
                "we'll wire up payments/airtel_money.py the same way."
            )
        else:
            raise ProviderError("Select MTN or Airtel.")

    else:  # yo_payments (default)
        from . import yo_payments as yo
        try:
            result = yo.initiate_mobile_money_charge(
                phone_number=phone_number, amount=amount,
                narrative='RestaurantFlow payment', external_reference=reference,
            )
        except yo.YoPaymentsNotConfigured as e:
            raise ProviderNotConfigured(str(e)) from e
        except yo.YoPaymentsError as e:
            raise ProviderError(str(e)) from e
        return {'provider_id': result['transaction_reference'], 'status': _YO_STATUS_MAP.get(result['status'], 'pending')}


def check_status(provider_id, network=None):
    provider = settings.MOBILE_MONEY_PROVIDER

    if provider == 'flutterwave':
        from . import flutterwave as flw
        try:
            return flw.verify_transaction(provider_id)
        except flw.FlutterwaveError as e:
            raise ProviderError(str(e)) from e

    elif provider == 'direct':
        network = (network or 'MTN').upper()
        if network == 'MTN':
            from . import mtn_momo as mtn
            try:
                status = mtn.check_transaction_status(provider_id)
            except mtn.MTNMoMoError as e:
                raise ProviderError(str(e)) from e
            return _MTN_STATUS_MAP.get(status, 'pending')
        raise ProviderError(f"Don't know how to check status for network '{network}'.")

    else:  # yo_payments
        from . import yo_payments as yo
        try:
            status = yo.check_transaction_status(provider_id)
        except yo.YoPaymentsError as e:
            raise ProviderError(str(e)) from e
        return _YO_STATUS_MAP.get(status, 'pending')
