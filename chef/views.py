from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from menu.models import Category, MenuItem, MenuItemImage, Allergen


def _is_chef_staff(user):
    return user.is_authenticated and user.role in ('kitchen', 'admin')


def _safe_next(request, default):
    next_url = request.GET.get('next') or request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return default


def chef_login(request):
    next_url = _safe_next(request, 'chef_board')
    if request.user.is_authenticated and _is_chef_staff(request.user):
        return redirect(next_url)

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and _is_chef_staff(user):
            auth_login(request, user)
            return redirect(next_url)
        error = 'Invalid credentials, or this account cannot manage the menu.'
    return render(request, 'chef/login.html', {'error': error, 'next': next_url})


def chef_logout(request):
    auth_logout(request)
    return redirect('chef_login')


@ensure_csrf_cookie
@login_required(login_url='chef_login')
def chef_board(request):
    if not _is_chef_staff(request.user):
        auth_logout(request)
        return redirect('chef_login')

    categories = Category.objects.prefetch_related('items__images', 'items__allergens').order_by('sort_order')
    return render(request, 'chef/board.html', {'categories': categories, 'user': request.user})


@login_required(login_url='chef_login')
def meal_form(request, item_id=None):
    if not _is_chef_staff(request.user):
        auth_logout(request)
        return redirect('chef_login')

    item = get_object_or_404(MenuItem, id=item_id) if item_id else None
    categories = Category.objects.order_by('sort_order')
    allergens = Allergen.objects.order_by('name')
    error = None

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        price = request.POST.get('price', '').strip()
        category_id = request.POST.get('category')
        available = request.POST.get('available') == 'on'
        allergen_ids = request.POST.getlist('allergens')

        if not name or not price or not category_id:
            error = 'Name, price, and category are all required.'
        else:
            try:
                price_value = float(price)
                if price_value < 0:
                    raise ValueError
            except ValueError:
                error = 'Enter a valid, non-negative price.'

        if not error:
            category = get_object_or_404(Category, id=category_id)
            if item is None:
                item = MenuItem.objects.create(
                    name=name, description=description, price=price_value,
                    category=category, available=available,
                )
            else:
                item.name = name
                item.description = description
                item.price = price_value
                item.category = category
                item.available = available
                item.save()

            item.allergens.set(allergen_ids)

            for photo in request.FILES.getlist('photos'):
                MenuItemImage.objects.create(menu_item=item, image=photo)

            return redirect('chef_board')

    return render(request, 'chef/meal_form.html', {
        'item': item,
        'categories': categories,
        'allergens': allergens,
        'selected_allergen_ids': set(item.allergens.values_list('id', flat=True)) if item else set(),
        'error': error,
    })


@login_required(login_url='chef_login')
@require_POST
def delete_meal(request, item_id):
    if not _is_chef_staff(request.user):
        return redirect('chef_login')
    item = get_object_or_404(MenuItem, id=item_id)
    item.delete()
    return redirect('chef_board')


@login_required(login_url='chef_login')
@require_POST
def delete_photo(request, image_id):
    if not _is_chef_staff(request.user):
        return redirect('chef_login')
    photo = get_object_or_404(MenuItemImage, id=image_id)
    item_id = photo.menu_item_id
    photo.image.delete(save=False)
    photo.delete()
    return redirect('chef_meal_edit', item_id=item_id)
