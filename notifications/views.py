from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import DeviceToken


class RegisterDeviceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        token = request.data.get('token')
        platform = request.data.get('platform', 'android')
        if not token:
            return Response({'detail': 'token is required'}, status=400)
        DeviceToken.objects.update_or_create(
            token=token, defaults={'user': request.user, 'platform': platform}
        )
        return Response({'status': 'registered'})
