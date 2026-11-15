from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'       # placed, not yet accepted by waiter/kitchen
        ACCEPTED = 'accepted', 'Accepted'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready'
        SERVED = 'served', 'Served'
        PAID = 'paid', 'Paid'
        CANCELLED = 'cancelled', 'Cancelled'

    class Channel(models.TextChoices):
        KIOSK = 'kiosk', 'Customer Kiosk'
        WAITER = 'waiter', 'Waiter App'
        QR = 'qr', 'QR Self-Order'

    table = models.ForeignKey('restaurant.Table', related_name='orders', on_delete=models.PROTECT)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WAITER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    customer_name = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} - Table {self.table.number} ({self.status})"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.exclude(status=OrderItem.Status.CANCELLED))

    # --- state transitions, validated server-side ---
    ALLOWED_TRANSITIONS = {
        Status.PENDING: {Status.ACCEPTED, Status.CANCELLED},
        Status.ACCEPTED: {Status.PREPARING, Status.CANCELLED},
        Status.PREPARING: {Status.READY, Status.CANCELLED},
        Status.READY: {Status.SERVED},
        Status.SERVED: {Status.PAID},
        Status.PAID: set(),
        Status.CANCELLED: set(),
    }

    def transition_to(self, new_status):
        if new_status not in self.ALLOWED_TRANSITIONS.get(self.status, set()):
            raise ValidationError(
                f"Cannot move order from '{self.status}' to '{new_status}'."
            )
        self.status = new_status
        self.save(update_fields=['status', 'updated_at'])

    def sync_status_from_items(self):
        """
        Derive order-level status from its item statuses. This always
        reflects ground truth, no matter how many steps it has to jump —
        e.g. if the kitchen and waiter raced ahead and served every item
        before anyone explicitly tapped 'Accept' on the order itself.

        This intentionally bypasses the single-step ALLOWED_TRANSITIONS
        gate that transition_to() uses. That gate exists to validate
        deliberate user actions (tapping Accept, tapping Cancel); this
        method instead represents a *derived* fact about the order, and
        should never get stuck behind a step nobody explicitly took.
        """
        if self.status in (self.Status.PAID, self.Status.CANCELLED):
            return  # never resurrect a finalized order

        statuses = set(self.items.exclude(status=OrderItem.Status.CANCELLED).values_list('status', flat=True))
        if not statuses:
            return

        if statuses == {OrderItem.Status.SERVED}:
            target = self.Status.SERVED
        elif statuses <= {OrderItem.Status.READY, OrderItem.Status.SERVED}:
            target = self.Status.READY
        elif statuses & {OrderItem.Status.PREPARING, OrderItem.Status.READY, OrderItem.Status.SERVED}:
            target = self.Status.PREPARING
        else:
            # every item is still pending — leave order status as-is;
            # moving PENDING -> ACCEPTED is a deliberate waiter action,
            # not something untouched items should trigger
            target = self.status

        if target != self.status:
            self.status = target
            self.save(update_fields=['status', 'updated_at'])


class OrderItem(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready'
        SERVED = 'served', 'Served'
        CANCELLED = 'cancelled', 'Cancelled'

    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey('menu.MenuItem', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)  # snapshot at order time
    notes = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name} ({self.status})"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def save(self, *args, **kwargs):
        if not self.unit_price:
            self.unit_price = self.menu_item.price
        super().save(*args, **kwargs)
