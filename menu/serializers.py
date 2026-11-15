from rest_framework import serializers
from .models import Allergen, Category, MenuItem


class AllergenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Allergen
        fields = ['id', 'name']


class MenuItemSerializer(serializers.ModelSerializer):
    allergens = AllergenSerializer(many=True, read_only=True)
    allergen_ids = serializers.PrimaryKeyRelatedField(
        queryset=Allergen.objects.all(), source='allergens', many=True, write_only=True, required=False
    )
    photos = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = ['id', 'category', 'name', 'description', 'price', 'image_url',
                   'available', 'allergens', 'allergen_ids', 'photos']

    def get_photos(self, obj):
        request = self.context.get('request')
        urls = []
        for photo in obj.images.all():
            url = photo.image.url
            urls.append(request.build_absolute_uri(url) if request else url)
        return urls


class CategorySerializer(serializers.ModelSerializer):
    items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'sort_order', 'items']
