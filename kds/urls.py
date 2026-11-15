from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.kitchen_login, name='kds_login'),
    path('logout/', views.kitchen_logout, name='kds_logout'),
    path('', views.kitchen_board, name='kds_board'),
    path('item/<int:item_id>/start/', views.start_preparing, name='kds_start_preparing'),
    path('item/<int:item_id>/ready/', views.mark_ready, name='kds_mark_ready'),
]
