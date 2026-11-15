from rest_framework import viewsets
from .models import Payment
from .serializers import PaymentSerializer
from accounts.permissions import IsCashierOrAdmin


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().prefetch_related('orders')
    serializer_class = PaymentSerializer
    permission_classes = [IsCashierOrAdmin]

    def perform_create(self, serializer):
        serializer.save(received_by=self.request.user)
