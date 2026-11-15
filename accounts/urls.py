from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import RegisterStaffView, MeView, StaffListView

urlpatterns = [
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', RegisterStaffView.as_view(), name='register_staff'),
    path('me/', MeView.as_view(), name='me'),
    path('staff/', StaffListView.as_view(), name='staff_list'),
]
