# sales/serializers.py
from decimal import Decimal
from rest_framework import serializers
from .models import Transaction, TransactionItem, TransactionHistory
import json
from django.contrib.auth.models import User
from customers.models import Customer
from customers.serializers import CustomerSerializer
from inventory.models import Product, UnitOfMeasure
from django.utils.translation import gettext_lazy as _
import logging

logger = logging.getLogger('sales')

class TransactionHistorySerializer(serializers.ModelSerializer):
    cashier = serializers.SerializerMethodField()
    details = serializers.SerializerMethodField()

    class Meta:
        model = TransactionHistory
        fields = ['id', 'transaction', 'action', 'cashier', 'details', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_cashier(self, obj):
        if obj.cashier:
            return {
                'id': obj.cashier.id,
                'username': obj.cashier.username,
                'full_name': obj.cashier.get_full_name() or obj.cashier.username
            }
        return None

    def get_details(self, obj):
        try:
            return json.loads(obj.details)
        except json.JSONDecodeError:
            return {'error': 'Некорректный формат деталей'}


class TransactionItemSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        help_text="ID товара из каталога"
    )
    quantity = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        min_value=Decimal('0.001'),
        help_text="Количество товара (можно дробное, если разрешено)"
    )
    unit_id = serializers.PrimaryKeyRelatedField(
        queryset=UnitOfMeasure.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        help_text="ID единицы измерения для продажи (опционально)"
    )

    def validate(self, data):
        product = data['product']
        quantity = data['quantity']
        unit = data.get('unit_id', product.unit)

        if unit.category != product.unit.category:
            raise serializers.ValidationError(
                _(f"Единица измерения {unit.name} не соответствует категории товара {product.unit.category.name}")
            )

        if quantity % 1 != 0 and not product.unit.category.allow_fraction:
            raise serializers.ValidationError(
                _(f"Для единицы {product.unit.short_name} нельзя использовать дробное количество")
            )

        real_qty = quantity * unit.conversion_factor
        if product.stock.quantity < real_qty:
            raise serializers.ValidationError(
                _(f"Недостаточно товара {product.name}. Доступно: {product.stock.quantity} {product.unit.short_name}")
            )

        data['real_quantity'] = real_qty
        data['used_unit'] = unit
        return data
# sales/serializers.py
class TransactionSerializer(serializers.ModelSerializer):
    items = TransactionItemSerializer(many=True)
    customer_id = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True
    )
    cashier = serializers.SerializerMethodField(read_only=True)
    history = TransactionHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Transaction
        fields = ['id', 'items', 'customer_id', 'cashier', 'payment_method', 'total_amount', 'status', 'created_at', 'history']
        read_only_fields = ['total_amount', 'status', 'created_at', 'cashier', 'history']

    def get_cashier(self, obj):
        if obj.cashier:
            return {
                'id': obj.cashier.id,
                'username': obj.cashier.username,
                'full_name': obj.cashier.get_full_name() or obj.cashier.username
            }
        return None

    def validate(self, data):
        items = data['items']
        for item in items:
            product = item['product']
            real_qty = item['real_quantity']
            if product.stock.quantity < real_qty:
                raise serializers.ValidationError(
                    _(f"Недостаточно товара {product.name}. Доступно: {product.stock.quantity} {product.unit.short_name}")
                )
        data['total_amount'] = self._calculate_total(items)
        return data

    def _calculate_total(self, items):
        total = Decimal('0.00')
        for item in items:
            product = item['product']
            qty = item['quantity']
            total += (product.sale_price * qty * item['used_unit'].conversion_factor / product.unit.conversion_factor)
        return round(total, 2)

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        user = self.context['request'].user

        if not user.is_authenticated:
            raise serializers.ValidationError(_("Требуется авторизация для создания продажи"))
        if not user.groups.filter(name__in=['admin', 'manager', 'cashier']).exists():
            raise serializers.ValidationError(_("У вас нет прав для создания продажи"))

        transaction = Transaction.objects.create(cashier=user, **validated_data)

        for item in items_data:
            product = item['product']
            qty = item['quantity']
            used_unit = item['used_unit']
            real_qty = item['real_quantity']

            TransactionItem.objects.create(
                transaction=transaction,
                product=product,
                quantity=qty,
                unit=used_unit,
                price=product.sale_price * used_unit.conversion_factor / product.unit.conversion_factor
            )
            product.stock.sell(real_qty)

        # Создаём запись в истории при создании транзакции
        TransactionHistory.objects.create(
            transaction=transaction,
            action='created',
            cashier=user,
            details=json.dumps({
                'total_amount': float(transaction.total_amount),
                'payment_method': transaction.payment_method,
                'items': [
                    {
                        'product': item.product.name,
                        'quantity': float(item.quantity),
                        'unit': item.unit.short_name,
                        'price': float(item.price)
                    } for item in transaction.items.all()
                ]
            })
        )
        logger.info(
            f"Продажа #{transaction.id} создана кассиром {user.username}: "
            f"сумма {transaction.total_amount}, метод оплаты {transaction.payment_method}"
        )
        return transaction
    
