from django.conf import settings
from django.db import models


class DeviceToken(models.Model):
    """FCM registration token per staff device, so push notifications reach the right role."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='device_tokens', on_delete=models.CASCADE)
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, default='android')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.platform}"
