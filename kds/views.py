from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from orders.models import Order, OrderItem


def _is_kitchen_staff(user):
    return user.is_authenticated and user.role in ('kitchen', 'admin')


def _safe_next(request, default):
    next_url = request.GET.get('next') or request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return default


def kitchen_login(request):
    next_url = _safe_next(request, 'kds_board')
    if request.user.is_authenticated and _is_kitchen_staff(request.user):
        return redirect(next_url)

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and _is_kitchen_staff(user):
            auth_login(request, user)
            return redirect(next_url)
        error = 'Invalid credentials, or this account is not a kitchen account.'
    return render(request, 'kds/login.html', {'error': error, 'next': next_url})


def kitchen_logout(request):
    auth_logout(request)
    return redirect('kds_login')


@ensure_csrf_cookie  # guarantees the CSRF cookie is set even with no <form> on the page
@login_required(login_url='kds_login')
def kitchen_board(request):
    if not _is_kitchen_staff(request.user):
        auth_logout(request)
        return redirect('kds_login')

    active_orders = (
        Order.objects.exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED, Order.Status.SERVED])
        .select_related('table')
        .prefetch_related('items__menu_item')
        .order_by('created_at')
    )
    return render(request, 'kds/board.html', {'orders': active_orders, 'user': request.user})


@login_required(login_url='kds_login')
@require_POST
def start_preparing(request, item_id):
    if not _is_kitchen_staff(request.user):
        return JsonResponse({'error': 'forbidden'}, status=403)
    item = get_object_or_404(OrderItem, id=item_id)
    item.status = OrderItem.Status.PREPARING
    item.save(update_fields=['status'])
    item.order.sync_status_from_items()
    return JsonResponse({'status': 'ok'})


@login_required(login_url='kds_login')
@require_POST
def mark_ready(request, item_id):
    if not _is_kitchen_staff(request.user):
        return JsonResponse({'error': 'forbidden'}, status=403)
    item = get_object_or_404(OrderItem, id=item_id)
    item.status = OrderItem.Status.READY
    item.save(update_fields=['status'])
    item.order.sync_status_from_items()

    from notifications.services import notify_role
    notify_role(
        'waiter', 'Order ready',
        f"{item.menu_item.name} ready for Table {item.order.table.number}"
    )
    return JsonResponse({'status': 'ok'})
