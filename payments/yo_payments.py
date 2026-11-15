"""
Yo! Payments (Uganda) mobile money integration.

Auth is a plain API username/password sent inside the XML request body —
no OAuth, no token refresh. Get these from your Yo! Payments dashboard
under API Access (this is a separate API username/password from the one
you use to log into the web portal — don't reuse your login password here).

Two calls used:
  1. ac_deposit_funds (acdepositfunds)        -> charges the customer
     (sends a USSD/on-screen prompt to their phone to approve)
  2. ac_transaction_check_status               -> polls for the real outcome

We always set NonBlocking=TRUE on the deposit call. Without it, Yo!
Payments holds the HTTP connection open until the customer responds —
which could be 30-90+ seconds, and would tie up a Django worker for that
whole time. Non-blocking returns immediately and we poll separately,
exactly like the Flutterwave flow this mirrors.

Docs: https://payments.yo.co.ug/resources/API.pdf
Reference implementation: https://github.com/YO-Uganda/YoPaymentsPython
"""
import requests
import xmltodict
from django.conf import settings

SANDBOX_URL = "https://sandbox.yo.co.ug/services/yopaymentsdev/task.php"
PRODUCTION_URL = "https://paymentsapi1.yo.co.ug/ybs/task.php"


class YoPaymentsError(Exception):
    """Raised when Yo! Payments rejects the request or is unreachable."""


class YoPaymentsNotConfigured(YoPaymentsError):
    """Raised when no API username/password has been set yet."""


def _base_url():
    return PRODUCTION_URL if settings.YO_PAYMENTS_USE_PRODUCTION else SANDBOX_URL


def _credentials():
    if not settings.YO_PAYMENTS_API_USERNAME or not settings.YO_PAYMENTS_API_PASSWORD:
        raise YoPaymentsNotConfigured(
            "Mobile money isn't set up yet — add YO_PAYMENTS_API_USERNAME and "
            "YO_PAYMENTS_API_PASSWORD to your .env. Find them in your Yo! Payments "
            "dashboard under 'API Access' (a separate API username/password from "
            "your portal login)."
        )
    return settings.YO_PAYMENTS_API_USERNAME, settings.YO_PAYMENTS_API_PASSWORD


def _post_xml(xml):
    try:
        response = requests.post(
            _base_url(),
            data=xml.encode('utf-8'),
            headers={"Content-type": "text/xml", "Content-transfer-encoding": "text"},
            timeout=20,
        )
    except requests.RequestException as e:
        raise YoPaymentsError(f"Could not reach Yo! Payments: {e}")

    try:
        parsed = xmltodict.parse(response.text)
        return parsed["AutoCreate"]["Response"]
    except Exception:
        raise YoPaymentsError(f"Unreadable response from Yo! Payments: {response.text[:300]}")


def initiate_mobile_money_charge(*, phone_number, amount, narrative, external_reference=None):
    """
    Sends a payment prompt to the customer's phone asking them to approve
    paying `amount` into your Yo! Payments account.

    Returns: {'transaction_reference': str, 'status': str}
    Raises: YoPaymentsError on failure (including not-yet-configured).
    """
    username, password = _credentials()
    xml = '<?xml version="1.0" encoding="UTF-8" ?>'
    xml += "<AutoCreate><Request>"
    xml += f"<APIUsername>{username}</APIUsername>"
    xml += f"<APIPassword>{password}</APIPassword>"
    xml += "<Method>acdepositfunds</Method>"
    xml += "<NonBlocking>TRUE</NonBlocking>"
    xml += f"<Amount>{amount}</Amount>"
    xml += f"<Account>{phone_number}</Account>"
    xml += f"<Narrative>{narrative}</Narrative>"
    if external_reference:
        xml += f"<ExternalReference>{external_reference}</ExternalReference>"
    xml += "</Request></AutoCreate>"

    data = _post_xml(xml)
    if data.get('Status') != 'OK':
        raise YoPaymentsError(data.get('StatusMessage', 'Yo! Payments rejected the charge.'))

    return {
        'transaction_reference': data.get('TransactionReference', ''),
        'status': (data.get('TransactionStatus') or 'PENDING').upper(),
    }


def check_transaction_status(transaction_reference):
    """
    Polls for the real outcome of a previously-initiated charge.
    Returns one of: 'SUCCEEDED', 'FAILED', 'PENDING', 'INDETERMINATE'.
    """
    username, password = _credentials()
    xml = '<?xml version="1.0" encoding="UTF-8" ?>'
    xml += "<AutoCreate><Request>"
    xml += f"<APIUsername>{username}</APIUsername>"
    xml += f"<APIPassword>{password}</APIPassword>"
    xml += "<Method>actransactioncheckstatus</Method>"
    xml += f"<TransactionReference>{transaction_reference}</TransactionReference>"
    xml += "</Request></AutoCreate>"

    data = _post_xml(xml)
    if data.get('Status') != 'OK':
        raise YoPaymentsError(data.get('StatusMessage', 'Could not check transaction status.'))

    return (data.get('TransactionStatus') or 'PENDING').upper()
