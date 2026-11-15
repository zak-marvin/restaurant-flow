from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.cashier_login, name='checkout_login'),
    path('logout/', views.cashier_logout, name='checkout_logout'),
    path('', views.cashier_board, name='checkout_board'),
    path('table/<int:table_id>/settle/', views.settle_table, name='checkout_settle'),
    path('payment/<int:payment_id>/status/', views.check_payment_status, name='checkout_payment_status'),
    path('webhook/flutterwave/', views.flutterwave_webhook, name='checkout_flutterwave_webhook'),
]
