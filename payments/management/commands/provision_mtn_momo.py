"""
One-time setup: creates an MTN MoMo "API User" + "API Key" using your
subscription key. You run this ONCE, then save the printed values into
your .env — after that, payments/mtn_momo.py handles everything else
(token refresh, charges, status checks) automatically.

Usage:
    python manage.py provision_mtn_momo
"""
import uuid
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "One-time: provisions an MTN MoMo API User + API Key for your sandbox subscription."

    def handle(self, *args, **options):
        if not settings.MTN_MOMO_SUBSCRIPTION_KEY:
            raise CommandError(
                "Set MTN_MOMO_SUBSCRIPTION_KEY in your .env first — that's the Primary Key "
                "from your MTN MoMo Developer dashboard under your Collection subscription."
            )

        base_url = "https://sandbox.momodeveloper.mtn.com"
        api_user_id = str(uuid.uuid4())
        headers = {
            "X-Reference-Id": api_user_id,
            "Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY,
            "Content-Type": "application/json",
        }

        self.stdout.write("Creating API user...")
        response = requests.post(
            f"{base_url}/v1_0/apiuser",
            json={"providerCallbackHost": settings.MTN_MOMO_CALLBACK_HOST or "restaurantflow.local"},
            headers=headers,
            timeout=15,
        )
        if response.status_code != 201:
            raise CommandError(f"Failed to create API user ({response.status_code}): {response.text}")

        self.stdout.write(self.style.SUCCESS(f"API user created: {api_user_id}"))

        self.stdout.write("Creating API key...")
        response = requests.post(
            f"{base_url}/v1_0/apiuser/{api_user_id}/apikey",
            headers={"Ocp-Apim-Subscription-Key": settings.MTN_MOMO_SUBSCRIPTION_KEY},
            timeout=15,
        )
        if response.status_code != 201:
            raise CommandError(f"Failed to create API key ({response.status_code}): {response.text}")

        api_key = response.json()['apiKey']

        self.stdout.write(self.style.SUCCESS("\nDone! Add these two lines to your .env:\n"))
        self.stdout.write(f"MTN_MOMO_API_USER={api_user_id}")
        self.stdout.write(f"MTN_MOMO_API_KEY={api_key}")
        self.stdout.write(self.style.WARNING("\nYou only ever need to run this once."))
