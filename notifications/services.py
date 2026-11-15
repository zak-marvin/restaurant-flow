"""
FCM push notifications.

Setup needed before this works for real:
  pip install firebase-admin
  Download a Firebase service account JSON from your Firebase console
  Set GOOGLE_APPLICATION_CREDENTIALS env var to its path

This module degrades gracefully (logs instead of sending) if firebase-admin
or credentials aren't configured, so the rest of the API still works without them.
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    if not firebase_admin._apps:
        cred_path = getattr(settings, 'FCM_CREDENTIALS_PATH', None)
        if cred_path:
            firebase_admin.initialize_app(credentials.Certificate(cred_path))
    # Only "available" if an app was actually initialised with credentials.
    FCM_AVAILABLE = bool(firebase_admin._apps)
except Exception:
    FCM_AVAILABLE = False


def notify_role(role, title, body, data=None):
    """Push a notification to every device registered to users with the given role."""
    from accounts.models import User
    from .models import DeviceToken

    tokens = list(DeviceToken.objects.filter(user__role=role).values_list('token', flat=True))
    if not tokens:
        return

    if not FCM_AVAILABLE:
        logger.info(f"[FCM disabled] Would notify role={role}: {title} - {body} -> {len(tokens)} device(s)")
        return

    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            tokens=tokens,
        )
        # send_multicast was removed from firebase-admin; send_each_for_multicast replaces it.
        messaging.send_each_for_multicast(message)
    except Exception:
        # A failed push must never break the request that triggered it
        # (for example placing an order).
        logger.exception("FCM send failed for role=%s", role)
