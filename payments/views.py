from rest_framework import mixins, viewsets
from .models import Payment
from .serializers import PaymentSerializer
from accounts.permissions import IsCashierOrAdmin


class PaymentViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                     mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Payments are an audit trail: create and read only (no edit or delete)."""
    queryset = Payment.objects.all().prefetch_related('orders')
    serializer_class = PaymentSerializer
    permission_classes = [IsCashierOrAdmin]

    def perform_create(self, serializer):
        serializer.save(received_by=self.request.user)
