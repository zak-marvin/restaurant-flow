from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('restaurant.urls')),
    path('api/', include('menu.urls')),
    path('api/', include('orders.urls')),
    path('api/', include('payments.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('kds/', include('kds.urls')),
    path('checkout/', include('checkout.urls')),
    path('chef/', include('chef.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
