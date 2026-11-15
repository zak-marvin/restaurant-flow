from django.db import models


class Allergen(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(Category, related_name='items', on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image_url = models.URLField(blank=True)  # kept for API back-compat; real photos live in MenuItemImage
    available = models.BooleanField(default=True)
    allergens = models.ManyToManyField(Allergen, blank=True, related_name='menu_items')

    class Meta:
        ordering = ['category__sort_order', 'name']

    def __str__(self):
        return self.name


class MenuItemImage(models.Model):
    """A chef can attach a few photos to each meal — first one uploaded
    acts as the cover photo shown in lists."""
    menu_item = models.ForeignKey(MenuItem, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='menu_items/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return f"Photo for {self.menu_item.name}"
