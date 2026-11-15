from django.db import transaction
from rest_framework import serializers
from .models import Order, OrderItem
from menu.models import MenuItem


class OrderItemWriteSerializer(serializers.Serializer):
    menu_item = serializers.PrimaryKeyRelatedField(queryset=MenuItem.objects.all())
    quantity = serializers.IntegerField(min_value=1, default=1)
    notes = serializers.CharField(allow_blank=True, required=False, default='')


class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source='menu_item.name', read_only=True)
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'menu_item', 'menu_item_name', 'quantity',
                   'unit_price', 'notes', 'status', 'subtotal']
        read_only_fields = ['unit_price']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    items_write = OrderItemWriteSerializer(many=True, write_only=True, required=False)
    total = serializers.ReadOnlyField()
    table_number = serializers.IntegerField(source='table.number', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'table', 'table_number', 'channel', 'status', 'customer_name',
                   'created_by', 'notes', 'created_at', 'updated_at', 'items', 'items_write', 'total']
        read_only_fields = ['status', 'created_by', 'created_at', 'updated_at']

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items_write', [])
        order = Order.objects.create(**validated_data)
        for item in items_data:
            OrderItem.objects.create(
                order=order,
                menu_item=item['menu_item'],
                quantity=item.get('quantity', 1),
                unit_price=item['menu_item'].price,
                notes=item.get('notes', ''),
            )
        # placing an order occupies the table
        table = order.table
        if table.status == table.Status.AVAILABLE:
            table.status = table.Status.OCCUPIED
            table.save(update_fields=['status'])

        from notifications.services import notify_role
        notify_role('kitchen', 'New order', f"Table {table.number} placed a new order", {'order_id': str(order.id)})
        return order
