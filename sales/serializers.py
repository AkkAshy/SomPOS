#sales/serializers.py
from rest_framework import serializers
from .models import Transaction, TransactionItem, TransactionHistory
from inventory.models import Product
from customers.models import Customer
from django.utils.translation import gettext_lazy as _
import logging
import json
from django.contrib.auth import get_user_model


User = get_user_model()

logger = logging.getLogger('sales')

class TransactionItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product'
    )

    class Meta:
        model = TransactionItem
        fields = ['product_id', 'quantity', 'price']

class TransactionSerializer(serializers.ModelSerializer):
    items = TransactionItemSerializer(many=True)
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
    new_customer = serializers.DictField(
        child=serializers.CharField(), required=False
    )

    class Meta:
        model = Transaction
        fields = ['id', 'cashier', 'total_amount', 'payment_method', 'status',
                 'customer', 'new_customer', 'items', 'created_at']
        read_only_fields = ['cashier', 'total_amount', 'created_at']

    def validate(self, data):
        items = data.get('items', [])
        customer = data.get('customer')
        new_customer = data.get('new_customer')
        payment_method = data.get('payment_method', 'cash')

        if payment_method == 'debt' and not (customer or new_customer):
            raise serializers.ValidationError(
                {"error": _("Для оплаты в долг требуется customer_id или new_customer")}
            )

        if new_customer:
            if not new_customer.get('full_name') or not new_customer.get('phone'):
                raise serializers.ValidationError(
                    {"new_customer": _("Поля full_name и phone обязательны")}
                )

        total_amount = 0
        for item in items:
            product = item['product']
            quantity = item['quantity']
            if product.stock.quantity < quantity:
                raise serializers.ValidationError(
                    {"items": _(f"Недостаточно товара {product.name} на складе")}
                )
            total_amount += product.sale_price * quantity

        data['total_amount'] = total_amount
        return data

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        customer = validated_data.pop('customer', None)
        new_customer = validated_data.pop('new_customer', None)
        user = self.context['request'].user

        if new_customer:
            phone = new_customer['phone']
            customer, created = Customer.objects.get_or_create(
                phone=phone,
                defaults={'full_name': new_customer['full_name']}
            )
        # ✅ customer уже объект, повторно его не ищем
        transaction = Transaction.objects.create(
            cashier=user,
            customer=customer,
            **validated_data
        )

        for item_data in items_data:
            product = item_data['product']
            quantity = item_data['quantity']
            TransactionItem.objects.create(
                transaction=transaction,
                product=product,
                quantity=quantity,
                price=product.sale_price
            )
            logger.info(
                f"Transaction item created by {user.username}. Transaction ID: {transaction.id}, "
                f"Product ID: {product.id}, Quantity: {quantity}"
            )

        transaction.process_sale()

        logger.info(
            f"Transaction created by {user.username}. ID: {transaction.id}, Total: {transaction.total_amount}"
        )
        return transaction

class TransactionHistorySerializer(serializers.ModelSerializer):
    parsed_details = serializers.SerializerMethodField()

    class Meta:
        model = TransactionHistory
        fields = ['id', 'transaction', 'action', 'parsed_details', 'created_at']

    def get_parsed_details(self, obj):
        try:
            return json.loads(obj.details)
        except json.JSONDecodeError:
            return {}

class CashierAggregateSerializer(serializers.Serializer):
    cashier_id = serializers.IntegerField()
    cashier_name = serializers.CharField()
    total_quantity = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)