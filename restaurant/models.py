import uuid
from django.db import models


class Table(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        OCCUPIED = 'occupied', 'Occupied'
        AWAITING_PAYMENT = 'awaiting_payment', 'Awaiting Payment'

    number = models.PositiveIntegerField(unique=True)
    capacity = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    qr_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        ordering = ['number']

    def __str__(self):
        return f"Table {self.number} ({self.status})"

    @property
    def unpaid_total(self):
        from orders.models import Order
        orders = Order.objects.filter(table=self).exclude(status=Order.Status.PAID).exclude(status=Order.Status.CANCELLED)
        return sum(o.total for o in orders)
