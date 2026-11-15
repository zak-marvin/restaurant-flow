from rest_framework import viewsets, permissions
from .models import Table
from .serializers import TableSerializer
from accounts.permissions import IsAdmin


class TableViewSet(viewsets.ModelViewSet):
    """
    Tables are read by everyone (waiters need to see status to seat customers),
    but only admins can add/edit/remove a table — that's a structural change
    to the restaurant layout (e.g. expansion), not a floor-staff action.
    """
    queryset = Table.objects.all()
    serializer_class = TableSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [permissions.IsAuthenticated()]
