from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets, permissions, status as http_status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .models import Order, OrderItem
from .serializers import OrderSerializer, OrderItemSerializer
from accounts.permissions import IsWaiterOrAdmin, IsKitchenOrAdmin


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().prefetch_related('items')
    serializer_class = OrderSerializer

    def get_permissions(self):
        if self.action in ['create']:
            return [permissions.IsAuthenticated()]  # waiter, or kiosk using a service account
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsWaiterOrAdmin()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    def get_queryset(self):
        qs = super().get_queryset()
        table_id = self.request.query_params.get('table')
        active_only = self.request.query_params.get('active')
        if table_id:
            qs = qs.filter(table_id=table_id)
        if active_only == 'true':
            qs = qs.exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED])
        return qs

    def _transition(self, request, pk, new_status):
        order = self.get_object()
        try:
            order.transition_to(new_status)
        except DjangoValidationError as e:
            raise ValidationError(e.message if hasattr(e, 'message') else str(e))
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=['post'], permission_classes=[IsWaiterOrAdmin])
    def accept(self, request, pk=None):
        return self._transition(request, pk, Order.Status.ACCEPTED)

    @action(detail=True, methods=['post'], permission_classes=[IsWaiterOrAdmin])
    def cancel(self, request, pk=None):
        return self._transition(request, pk, Order.Status.CANCELLED)


class OrderItemViewSet(viewsets.ModelViewSet):
    """Kitchen-facing item-level updates: each dish moves through its own status."""
    queryset = OrderItem.objects.all().select_related('order', 'menu_item')
    serializer_class = OrderItemSerializer

    def get_permissions(self):
        if self.action in ['start_preparing', 'mark_ready']:
            return [IsKitchenOrAdmin()]
        if self.action in ['serve']:
            return [IsWaiterOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        kitchen_queue = self.request.query_params.get('kitchen_queue')
        if kitchen_queue == 'true':
            qs = qs.exclude(status__in=[OrderItem.Status.SERVED, OrderItem.Status.CANCELLED])
        return qs

    def _set_item_status(self, pk, new_status):
        item = self.get_object()
        item.status = new_status
        item.save(update_fields=['status'])
        item.order.sync_status_from_items()
        return Response(OrderItemSerializer(item).data)

    @action(detail=True, methods=['post'])
    def start_preparing(self, request, pk=None):
        return self._set_item_status(pk, OrderItem.Status.PREPARING)

    @action(detail=True, methods=['post'])
    def mark_ready(self, request, pk=None):
        response = self._set_item_status(pk, OrderItem.Status.READY)
        item = self.get_object()
        from notifications.services import notify_role
        notify_role('waiter', 'Order ready', f"{item.menu_item.name} ready for Table {item.order.table.number}")
        return response

    @action(detail=True, methods=['post'])
    def serve(self, request, pk=None):
        return self._set_item_status(pk, OrderItem.Status.SERVED)
