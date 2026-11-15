import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_POST

from orders.models import Order
from payments import mobile_money as momo
from payments.models import Payment
from restaurant.models import Table


def _is_cashier_staff(user):
    return user.is_authenticated and user.role in ('cashier', 'admin')


def _safe_next(request, default):
    next_url = request.GET.get('next') or request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return default


def cashier_login(request):
    next_url = _safe_next(request, 'checkout_board')
    if request.user.is_authenticated and _is_cashier_staff(request.user):
        return redirect(next_url)

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and _is_cashier_staff(user):
            auth_login(request, user)
            return redirect(next_url)
        error = 'Invalid credentials, or this account is not a cashier account.'
    return render(request, 'checkout/login.html', {'error': error, 'next': next_url})


def cashier_logout(request):
    auth_logout(request)
    return redirect('checkout_login')


def _unpaid_orders_for_table(table):
    return (
        Order.objects.filter(table=table)
        .exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED])
        .prefetch_related('items__menu_item')
        .order_by('created_at')
    )


def _finalize_payment(payment, orders, table):
    """Marks the given orders paid and frees the table if nothing else is unpaid."""
    for order in orders:
        order.transition_to(Order.Status.PAID)
    if not _unpaid_orders_for_table(table).exists():
        table.status = Table.Status.AVAILABLE
        table.save(update_fields=['status'])


@ensure_csrf_cookie
@login_required(login_url='checkout_login')
def cashier_board(request):
    if not _is_cashier_staff(request.user):
        auth_logout(request)
        return redirect('checkout_login')

    tables_with_bills = []
    occupied_tables = Table.objects.exclude(status=Table.Status.AVAILABLE).order_by('number')
    for table in occupied_tables:
        unpaid_orders = list(_unpaid_orders_for_table(table))
        if not unpaid_orders:
            continue
        all_served = all(o.status == Order.Status.SERVED for o in unpaid_orders)
        total = sum(o.total for o in unpaid_orders)
        pending_payment = Payment.objects.filter(table=table, status=Payment.Status.PENDING).first()
        tables_with_bills.append({
            'table': table,
            'orders': unpaid_orders,
            'total': total,
            'ready_to_settle': all_served,
            'pending_payment': pending_payment,
        })

    return render(request, 'checkout/board.html', {
        'bills': tables_with_bills,
        'user': request.user,
        'methods': Payment.Method.choices,
    })


@login_required(login_url='checkout_login')
@require_POST
@transaction.atomic
def settle_table(request, table_id):
    if not _is_cashier_staff(request.user):
        return JsonResponse({'error': 'forbidden'}, status=403)

    table = get_object_or_404(Table, id=table_id)
    method = request.POST.get('method', Payment.Method.CASH)
    if method not in dict(Payment.Method.choices):
        return JsonResponse({'error': f"Unknown payment method '{method}'."}, status=400)

    # Don't let a second settle attempt fire while a mobile money charge for
    # this table is already waiting on the customer's approval.
    if Payment.objects.filter(table=table, status=Payment.Status.PENDING).exists():
        return JsonResponse({'error': 'A payment is already in progress for this table.'}, status=400)

    unpaid_orders = list(_unpaid_orders_for_table(table))
    if not unpaid_orders:
        return JsonResponse({'error': 'No unpaid orders for this table.'}, status=400)

    not_served = [o for o in unpaid_orders if o.status != Order.Status.SERVED]
    if not_served:
        return JsonResponse({
            'error': f"Order #{not_served[0].id} is still '{not_served[0].status}' — "
                     f"all items must be served before settling the bill."
        }, status=400)

    total = sum(o.total for o in unpaid_orders)

    # ---------- Cash: ask how much was handed over, compute change ----------
    if method == Payment.Method.CASH:
        try:
            tendered = Decimal(request.POST.get('amount_tendered', ''))
        except (InvalidOperation, TypeError):
            return JsonResponse({'error': 'Enter the amount the customer handed over.'}, status=400)
        if tendered < total:
            return JsonResponse({
                'error': f"Amount tendered (UGX {tendered:,.0f}) is less than the total (UGX {total:,.0f})."
            }, status=400)
        change = tendered - total

        payment = Payment.objects.create(
            table=table, amount=total, method=method, status=Payment.Status.SUCCESSFUL,
            amount_tendered=tendered, change_given=change, received_by=request.user,
        )
        payment.orders.set(unpaid_orders)
        _finalize_payment(payment, unpaid_orders, table)
        return JsonResponse({
            'status': 'ok', 'payment_id': payment.id, 'table_number': table.number,
            'amount': str(total), 'change_given': str(change),
        })

    # ---------- Card: recorded manually for now, no terminal integration yet ----------
    elif method == Payment.Method.CARD:
        payment = Payment.objects.create(
            table=table, amount=total, method=method, status=Payment.Status.SUCCESSFUL,
            received_by=request.user,
        )
        payment.orders.set(unpaid_orders)
        _finalize_payment(payment, unpaid_orders, table)
        return JsonResponse({'status': 'ok', 'payment_id': payment.id, 'table_number': table.number, 'amount': str(total)})

    # ---------- Mobile Money: charge via whichever provider is configured ----------
    else:
        phone_number = request.POST.get('phone_number', '').strip()
        network = request.POST.get('network', '').strip().upper()
        if not phone_number:
            return JsonResponse({'error': "Enter the customer's mobile money phone number."}, status=400)
        # Only the 'direct' provider actually needs to know which network to
        # route to (MTN vs Airtel are separate integrations). Aggregators
        # like Yo! Payments and Flutterwave handle network detection themselves.
        if settings.MOBILE_MONEY_PROVIDER == 'direct' and network not in ('MTN', 'AIRTEL'):
            return JsonResponse({'error': 'Select MTN or Airtel.'}, status=400)

        payment = Payment.objects.create(
            table=table, amount=total, method=method, status=Payment.Status.PENDING,
            phone_number=phone_number, network=network,
            provider=settings.MOBILE_MONEY_PROVIDER, received_by=request.user,
        )
        payment.orders.set(unpaid_orders)

        reference = f"rflow-{payment.id}"
        try:
            result = momo.initiate_charge(phone_number=phone_number, amount=total, reference=reference, network=network)
        except momo.ProviderError as e:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=['status'])
            return JsonResponse({'error': str(e)}, status=400)

        payment.provider_reference = result['provider_id']
        payment.save(update_fields=['provider_reference'])

        return JsonResponse({
            'status': 'pending',
            'payment_id': payment.id,
            'message': f'Payment request sent to {phone_number}. Waiting for the customer to approve…',
        })


@login_required(login_url='checkout_login')
def check_payment_status(request, payment_id):
    """Polled by the checkout page while a mobile money payment is pending."""
    if not _is_cashier_staff(request.user):
        return JsonResponse({'error': 'forbidden'}, status=403)

    payment = get_object_or_404(Payment, id=payment_id)

    if payment.status == Payment.Status.PENDING:
        try:
            result = momo.check_status(payment.provider_reference, network=payment.network)
        except momo.ProviderError as e:
            # Transient — don't fail the poll, just report still-pending with a note.
            return JsonResponse({'status': 'pending', 'note': str(e)})

        if result == 'successful':
            payment.status = Payment.Status.SUCCESSFUL
            payment.save(update_fields=['status'])
            _finalize_payment(payment, list(payment.orders.all()), payment.table)
        elif result == 'failed':
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=['status'])

    return JsonResponse({
        'status': payment.status,
        'payment_id': payment.id,
        'table_number': payment.table.number,
        'amount': str(payment.amount),
    })


@csrf_exempt
@require_POST
def flutterwave_webhook(request):
    """
    Flutterwave-specific push notification handler — only relevant if
    MOBILE_MONEY_PROVIDER=flutterwave. Needs a public URL (e.g. via ngrok
    in dev) configured in your Flutterwave dashboard, plus
    FLUTTERWAVE_WEBHOOK_HASH set to match.

    Yo! Payments doesn't use this — its IPN mechanism uses certificate-based
    signature verification instead of a simple hash, and since the checkout
    page's 3-second polling already confirms payments reliably without it,
    we haven't wired that up. Polling works fine on its own.
    """
    signature = request.headers.get('verif-hash', '')
    if not settings.FLUTTERWAVE_WEBHOOK_HASH or signature != settings.FLUTTERWAVE_WEBHOOK_HASH:
        return JsonResponse({'error': 'invalid signature'}, status=401)

    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'error': 'invalid payload'}, status=400)

    data = payload.get('data', {})
    tx_ref = data.get('tx_ref')
    status = data.get('status')

    try:
        # Charges are created with tx_ref "rflow-<payment id>" (see settle_table).
        payment_id = int(str(tx_ref).rsplit('-', 1)[-1]) if str(tx_ref).startswith('rflow-') else None
        payment = Payment.objects.get(id=payment_id, provider='flutterwave')
    except (Payment.DoesNotExist, TypeError, ValueError):
        return JsonResponse({'error': 'unknown tx_ref'}, status=404)

    if payment.status == Payment.Status.PENDING:
        if status == 'successful':
            payment.status = Payment.Status.SUCCESSFUL
            payment.save(update_fields=['status'])
            _finalize_payment(payment, list(payment.orders.all()), payment.table)
        elif status == 'failed':
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=['status'])

    return JsonResponse({'status': 'received'})
