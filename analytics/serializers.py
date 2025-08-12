# analytics/serializers.py
from rest_framework import serializers
from .models import SalesSummary, ProductAnalytics, CustomerAnalytics
from inventory.serializers import ProductSerializer
from customers.models import Customer
from django.utils.translation import gettext_lazy as _

from sales.models import Transaction, TransactionHistory

class SalesSummarySerializer(serializers.ModelSerializer):
    payment_method_display = serializers.CharField(
        source='get_payment_method_display', read_only=True
    )

    class Meta:
        model = SalesSummary
        fields = ['date', 'total_amount', 'total_transactions', 'total_items_sold',
                  'payment_method', 'payment_method_display']

class ProductAnalyticsSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = ProductAnalytics
        fields = ['product', 'date', 'quantity_sold', 'revenue']

class CustomerAnalyticsSerializer(serializers.ModelSerializer):
    customer = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = CustomerAnalytics
        fields = ['customer', 'date', 'total_purchases', 'transaction_count', 'debt_added']


class TransactionsHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionHistory
        fields = ['customer', 'cashier', 'date', 'total_purchases', 'transaction_count', 'debt_added']


class Transaction(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['customer', 'cashier', 'date', 'total_purchases', 'transaction_count', 'debt_added']