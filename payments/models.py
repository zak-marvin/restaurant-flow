from django.conf import settings
from django.db import models


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Cash'
        MOBILE_MONEY = 'mobile_money', 'Mobile Money'
        CARD = 'card', 'Card'

    class Status(models.TextChoices):
        SUCCESSFUL = 'successful', 'Successful'   # cash/card settle instantly
        PENDING = 'pending', 'Pending'             # mobile money: waiting on customer approval
        FAILED = 'failed', 'Failed'

    table = models.ForeignKey('restaurant.Table', related_name='payments', on_delete=models.PROTECT)
    orders = models.ManyToManyField('orders.Order', related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESSFUL)
    reference = models.CharField(max_length=120, blank=True)  # e.g. mobile money tx_ref
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    paid_at = models.DateTimeField(auto_now_add=True)

    # cash-specific: what the customer physically handed over and the change given
    amount_tendered = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    change_given = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # mobile-money-specific: the active provider and its own reference for
    # this charge, used to poll for status
    provider = models.CharField(max_length=20, blank=True, default='')  # 'yo_payments', 'flutterwave', 'direct'
    provider_reference = models.CharField(max_length=120, blank=True, default='')
    network = models.CharField(max_length=20, blank=True, default='')  # 'MTN' or 'AIRTEL', when relevant
    phone_number = models.CharField(max_length=20, blank=True, default='')

    def __str__(self):
        return f"Payment {self.amount} for Table {self.table.number} ({self.status})"
