from rest_framework.routers import DefaultRouter
from .views import AllergenViewSet, CategoryViewSet, MenuItemViewSet

router = DefaultRouter()
router.register(r'allergens', AllergenViewSet, basename='allergen')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'items', MenuItemViewSet, basename='menuitem')
urlpatterns = router.urls
