from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import User
from .serializers import UserSerializer, CreateUserSerializer
from .permissions import IsAdmin


class RegisterStaffView(generics.CreateAPIView):
    """Admin creates staff accounts (waiter / kitchen / cashier / admin)."""
    queryset = User.objects.all()
    serializer_class = CreateUserSerializer
    permission_classes = [IsAdmin]


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class StaffListView(generics.ListAPIView):
    queryset = User.objects.all().order_by('role', 'username')
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
