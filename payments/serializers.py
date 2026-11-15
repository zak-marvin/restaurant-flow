from django.db import transaction
from rest_framework import serializers
from .models import Payment
from orders.models import Order


class PaymentSerializer(serializers.ModelSerializer):
    order_ids = serializers.PrimaryKeyRelatedField(
        queryset=Order.objects.all(), source='orders', many=True, write_only=True
    )

    class Meta:
        model = Payment
        fields = ['id', 'table', 'orders', 'order_ids', 'amount', 'method',
                   'reference', 'received_by', 'paid_at']
        read_only_fields = ['orders', 'received_by', 'paid_at']

    def validate(self, attrs):
        if attrs.get('method') == Payment.Method.MOBILE_MONEY:
            raise serializers.ValidationError(
                "Mobile money must be taken through the cashier checkout page (/checkout/), "
                "which sends the charge and waits for the provider to confirm it."
            )
        orders = attrs.get('orders', [])
        if not orders:
            raise serializers.ValidationError("At least one order must be included in the payment.")
        table = attrs['table']
        for order in orders:
            if order.table_id != table.id:
                raise serializers.ValidationError(f"Order #{order.id} does not belong to Table {table.number}.")
            if order.status != Order.Status.SERVED:
                raise serializers.ValidationError(
                    f"Order #{order.id} is '{order.status}' — only served orders can be paid for."
                )
        expected = sum(o.total for o in orders)
        if attrs['amount'] != expected:
            raise serializers.ValidationError(
                f"Amount {attrs['amount']} does not match order total {expected}."
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        orders = validated_data.pop('orders')
        payment = Payment.objects.create(**validated_data)
        payment.orders.set(orders)
        for order in orders:
            order.transition_to(Order.Status.PAID)
        table = payment.table
        remaining_unpaid = table.orders.exclude(
            status__in=[Order.Status.PAID, Order.Status.CANCELLED]
        ).exists()
        if not remaining_unpaid:
            table.status = table.Status.AVAILABLE
            table.save(update_fields=['status'])
        return payment
