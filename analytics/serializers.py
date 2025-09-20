# analytics/serializers.py
from rest_framework import serializers
from .models import SalesSummary, ProductAnalytics, CustomerAnalytics, SupplierAnalytics, CashRegister, CashHistory
from inventory.serializers import ProductSerializer
from customers.models import Customer
from django.utils.translation import gettext_lazy as _

from sales.models import Transaction, TransactionHistory
from stores.mixins import StoreSerializerMixin
from rest_framework.response import Response

class CashRegisterSerializer(StoreSerializerMixin, serializers.ModelSerializer):
    """
    ✅ СЕРИАЛИЗАТОР КАССЫ — баланс и снятие
    """
    # Для withdraw: amount и notes
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    
    # Читаемые поля
    store_name = serializers.CharField(source='store.name', read_only=True)
    balance_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = CashRegister
        fields = [
            'id', 'store', 'store_name', 'date_opened', 'current_balance', 'target_balance',
            'last_updated', 'is_open', 'financial_summary',
            'amount', 'notes', 'balance_formatted'
        ]
        read_only_fields = ['id', 'store', 'date_opened', 'current_balance', 'target_balance',
                            'last_updated', 'is_open', 'financial_summary', 'balance_formatted']

    def get_balance_formatted(self, obj):
        """Форматированный баланс для фронта"""
        return f"{obj.current_balance:,.0f} сум"

    def create(self, validated_data):
        # При создании — открываем новую смену
        store = self.context['request'].user.current_store
        validated_data['store'] = store
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Для POST withdraw: используем метод withdraw
        amount = validated_data.pop('amount', None)
        notes = validated_data.pop('notes', '')
        user = self.context['request'].user
        
        if amount is not None:
            withdrawn = instance.withdraw(amount, user, notes)
            return Response({'withdrawn': withdrawn, 'new_balance': instance.current_balance})
        
        return super().update(instance, validated_data)

class SupplierAnalyticsSerializer(serializers.ModelSerializer):
    supplier_display = serializers.CharField(source='supplier', read_only=True)  # Для удобства

    class Meta:

        model = SupplierAnalytics
        fields = [
            'date', 'supplier', 'supplier_display',
            'total_quantity_sold', 'total_revenue', 'total_cost', 'total_margin',
            'products_count', 'transactions_count', 'unique_products_sold',
            'average_margin_percentage', 'turnover_rate'
        ]


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


class CashHistorySerializer(serializers.ModelSerializer):
    operation_display = serializers.CharField(source='get_operation_type_display', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    timestamp_formatted = serializers.DateTimeField(
        source='timestamp', format='%Y-%m-%d %H:%M:%S', read_only=True
    )

    class Meta:
        model = CashHistory
        fields = [
            'id', 'operation_type', 'operation_display', 'amount', 'user', 'user_name',
            'timestamp', 'timestamp_formatted', 'notes', 'balance_before', 'balance_after'
        ]

class CashRegisterCloseSerializer(serializers.Serializer):
    """Для закрытия смены"""
    actual_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="Закрытие смены")