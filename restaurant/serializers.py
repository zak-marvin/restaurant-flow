from rest_framework import serializers
from .models import Table


class TableSerializer(serializers.ModelSerializer):
    unpaid_total = serializers.ReadOnlyField()

    class Meta:
        model = Table
        fields = ['id', 'number', 'capacity', 'status', 'qr_token', 'unpaid_total']
        read_only_fields = ['qr_token']
