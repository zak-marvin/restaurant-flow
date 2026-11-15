import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurantflow.settings')
django.setup()

from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile

# Smallest valid 1x1 PNG, used to test real file uploads without needing a real image file
TINY_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
    b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)


class ChefMenuTest(TestCase):
    def setUp(self):
        from accounts.models import User
        from menu.models import Category, Allergen

        self.client = Client()
        self.chef = User.objects.create(username='chef1', role='kitchen')
        self.chef.set_password('pass1234')
        self.chef.save()
        self.waiter = User.objects.create(username='chef_test_waiter', role='waiter')
        self.waiter.set_password('pass1234')
        self.waiter.save()

        self.category = Category.objects.create(name='Chef Test Category', sort_order=1)
        self.nuts = Allergen.objects.create(name='Nuts')
        self.dairy = Allergen.objects.create(name='Dairy')

        self.client.post('/chef/login/', {'username': 'chef1', 'password': 'pass1234'})

    def _photo(self, name='photo.png'):
        return SimpleUploadedFile(name, TINY_PNG, content_type='image/png')

    def test_waiter_blocked_from_chef_pages(self):
        print("\n[Chef] Waiter role blocked")
        self.client.logout()
        self.client.post('/chef/login/', {'username': 'chef_test_waiter', 'password': 'pass1234'})
        r = self.client.get('/chef/')
        self.assertEqual(r.status_code, 302)
        self.assertNotEqual(r.url, '/chef/')
        print("  ✓ Waiter login does not reach the chef menu board")

    def test_create_meal_with_photo_and_allergens(self):
        print("[Chef] Create meal with photo + allergens")
        r = self.client.post('/chef/meal/new/', {
            'name': 'Chef Test Pizza',
            'description': 'Wood-fired, very good',
            'price': '28000',
            'category': self.category.id,
            'allergens': [self.nuts.id, self.dairy.id],
            'available': 'on',
            'photos': [self._photo()],
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, '/chef/')

        from menu.models import MenuItem
        item = MenuItem.objects.get(name='Chef Test Pizza')
        self.assertEqual(float(item.price), 28000)
        self.assertEqual(item.allergens.count(), 2)
        self.assertEqual(item.images.count(), 1)
        print(f"  ✓ Created '{item.name}' with {item.allergens.count()} allergens and {item.images.count()} photo")

        r = self.client.get('/chef/')
        self.assertContains(r, 'Chef Test Pizza')
        self.assertContains(r, 'Nuts')
        print("  ✓ Board shows the new meal with its allergen tags")

    def test_edit_meal_updates_fields_and_adds_photo(self):
        print("[Chef] Edit meal - update fields, add a second photo")
        from menu.models import MenuItem
        item = MenuItem.objects.create(name='Chef Test Burger', price=15000, category=self.category)
        item.images.create(image=self._photo('first.png'))

        r = self.client.post(f'/chef/meal/{item.id}/edit/', {
            'name': 'Chef Test Burger Deluxe',
            'description': 'Now with extra cheese',
            'price': '19000',
            'category': self.category.id,
            'allergens': [self.dairy.id],
            'available': 'on',
            'photos': [self._photo('second.png')],
        })
        self.assertEqual(r.status_code, 302)

        item.refresh_from_db()
        self.assertEqual(item.name, 'Chef Test Burger Deluxe')
        self.assertEqual(float(item.price), 19000)
        self.assertEqual(item.images.count(), 2)
        self.assertEqual(list(item.allergens.values_list('name', flat=True)), ['Dairy'])
        print(f"  ✓ Updated name/price, now has {item.images.count()} photos and allergens={list(item.allergens.values_list('name', flat=True))}")

    def test_delete_individual_photo(self):
        print("[Chef] Delete a single photo without deleting the meal")
        from menu.models import MenuItem
        item = MenuItem.objects.create(name='Chef Test Salad', price=8000, category=self.category)
        photo = item.images.create(image=self._photo())

        r = self.client.post(f'/chef/photo/{photo.id}/delete/')
        self.assertEqual(r.status_code, 302)

        item.refresh_from_db()
        self.assertEqual(item.images.count(), 0)
        self.assertTrue(MenuItem.objects.filter(id=item.id).exists())
        print("  ✓ Photo removed, meal itself untouched")

    def test_delete_meal_removes_it_from_menu(self):
        print("[Chef] Delete a meal entirely")
        from menu.models import MenuItem
        item = MenuItem.objects.create(name='Chef Test Soda', price=3000, category=self.category)

        r = self.client.post(f'/chef/meal/{item.id}/delete/')
        self.assertEqual(r.status_code, 302)
        self.assertFalse(MenuItem.objects.filter(id=item.id).exists())
        print("  ✓ Meal deleted")

        r = self.client.get('/chef/')
        self.assertNotContains(r, 'Chef Test Soda')
        print("  ✓ Board no longer shows the deleted meal")

    def test_invalid_price_rejected(self):
        print("[Chef] Invalid price rejected with a clear error")
        r = self.client.post('/chef/meal/new/', {
            'name': 'Bad Meal', 'description': '', 'price': 'not-a-number',
            'category': self.category.id, 'available': 'on',
        })
        self.assertEqual(r.status_code, 200)  # re-renders form, doesn't redirect
        self.assertContains(r, 'valid')
        from menu.models import MenuItem
        self.assertFalse(MenuItem.objects.filter(name='Bad Meal').exists())
        print("  ✓ Invalid price correctly rejected, no meal created")
