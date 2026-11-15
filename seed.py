"""
Run with: python seed.py
Seeds the database with realistic restaurant data for testing.
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurantflow.settings')
django.setup()

from accounts.models import User
from restaurant.models import Table
from menu.models import Allergen, Category, MenuItem

print("Seeding users...")
def make_user(username, role, password='pass1234'):
    u, created = User.objects.get_or_create(username=username, defaults={'role': role})
    if created:
        u.set_password(password)
        u.first_name = username.capitalize()
        u.save()
    return u

admin   = make_user('admin',   'admin')
waiter1 = make_user('waiter1', 'waiter')
waiter2 = make_user('waiter2', 'waiter')
kitchen = make_user('kitchen', 'kitchen')
cashier = make_user('cashier', 'cashier')
print(f"  Users: {User.objects.count()}")

print("Seeding tables...")
for number in range(1, 13):
    Table.objects.get_or_create(number=number, defaults={'capacity': 4 if number <= 8 else 6})
print(f"  Tables: {Table.objects.count()}")

print("Seeding allergens...")
allergen_names = ['Gluten', 'Dairy', 'Eggs', 'Nuts', 'Peanuts', 'Soy', 'Fish', 'Shellfish', 'Sesame']
allergens = {}
for name in allergen_names:
    a, _ = Allergen.objects.get_or_create(name=name)
    allergens[name] = a
print(f"  Allergens: {Allergen.objects.count()}")

print("Seeding menu...")
food, _ = Category.objects.get_or_create(name='Food', defaults={'sort_order': 1})
drinks, _ = Category.objects.get_or_create(name='Drinks', defaults={'sort_order': 2})
extras, _ = Category.objects.get_or_create(name='Extras', defaults={'sort_order': 3})

menu_data = [
    # (name, description, price, category, allergen_list)
    ('Rolex', 'Chapati rolled with eggs & vegetables', 5000, food, ['Gluten', 'Eggs']),
    ('Chicken Burger', 'Grilled chicken fillet, lettuce, tomato, special sauce', 18000, food, ['Gluten', 'Dairy', 'Eggs', 'Sesame']),
    ('Beef Burger', 'Beef patty, cheese, pickles, mustard', 20000, food, ['Gluten', 'Dairy', 'Eggs', 'Sesame']),
    ('Chips (Large)', 'Crispy deep-fried potato chips', 8000, food, []),
    ('Chips (Small)', 'Crispy deep-fried potato chips', 5000, food, []),
    ('Grilled Tilapia', 'Whole tilapia, served with ugali & greens', 25000, food, ['Fish']),
    ('Matoke', 'Steamed green bananas with groundnut sauce', 10000, food, ['Peanuts']),
    ('Pilau', 'Spiced beef rice', 15000, food, ['Gluten']),
    ('G-nut Sauce + Posho', 'Traditional groundnut sauce with posho', 8000, food, ['Peanuts']),
    ('Salad', 'Fresh garden salad', 6000, food, []),
    ('Soda (300ml)', 'Pepsi, Mirinda, 7Up, Sprite', 3000, drinks, []),
    ('Water (500ml)', 'Rwenzori or Dasani chilled water', 2000, drinks, []),
    ('Fresh Juice', 'Passion, mango or pineapple — blended fresh', 5000, drinks, []),
    ('Milk Tea (Chai)', 'Spiced masala tea with full cream milk', 3000, drinks, ['Dairy']),
    ('Coffee', 'Ugandan arabica, black or with milk', 4000, drinks, ['Dairy']),
    ('Beer (500ml)', 'Nile Special, Bell or Club', 6000, drinks, ['Gluten']),
    ('Ketchup', 'Heinz tomato ketchup', 500, extras, []),
    ('Chilli Sauce', 'House-made hot sauce', 500, extras, []),
    ('Extra Bread', 'Sliced white bread (2 pcs)', 1000, extras, ['Gluten', 'Dairy', 'Eggs']),
]

for name, desc, price, cat, allergen_list in menu_data:
    item, _ = MenuItem.objects.get_or_create(
        name=name,
        defaults={'description': desc, 'price': price, 'category': cat}
    )
    for a_name in allergen_list:
        item.allergens.add(allergens[a_name])

print(f"  Menu items: {MenuItem.objects.count()}")
print("\n✅ Seed complete! Login credentials (all passwords: pass1234):")
print("   admin / pass1234   → admin role")
print("   waiter1 / pass1234 → waiter role")
print("   kitchen / pass1234 → kitchen role")
print("   cashier / pass1234 → cashier role")
