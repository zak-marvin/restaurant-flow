from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        WAITER = 'waiter', 'Waiter'
        KITCHEN = 'kitchen', 'Kitchen'
        CASHIER = 'cashier', 'Cashier'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.WAITER)

    def __str__(self):
        return f"{self.username} ({self.role})"
