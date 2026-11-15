import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurantflow.settings')

app = Celery('restaurantflow')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'check-stale-orders-every-2-minutes': {
        'task': 'orders.tasks.flag_stale_orders',
        'schedule': crontab(minute='*/2'),
    },
}
