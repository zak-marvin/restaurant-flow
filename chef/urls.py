from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.chef_login, name='chef_login'),
    path('logout/', views.chef_logout, name='chef_logout'),
    path('', views.chef_board, name='chef_board'),
    path('meal/new/', views.meal_form, name='chef_meal_new'),
    path('meal/<int:item_id>/edit/', views.meal_form, name='chef_meal_edit'),
    path('meal/<int:item_id>/delete/', views.delete_meal, name='chef_meal_delete'),
    path('photo/<int:image_id>/delete/', views.delete_photo, name='chef_photo_delete'),
]
