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
    """
    Упрощенный сериализатор - ТОЛЬКО product_id и quantity
    Цена НЕ принимается с фронта
    """
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        help_text="ID товара"
    )
    quantity = serializers.IntegerField(
        min_value=1,
        help_text="Количество товара"
    )
    # ✅ УБИРАЕМ поле price из входных данных!
    # price будет только для чтения при выводе
    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,  # ← ТОЛЬКО ДЛЯ ЧТЕНИЯ!
        help_text="Цена за единицу (берется из товара)"
    )

    class Meta:
        model = TransactionItem
        fields = ['product_id', 'quantity', 'price']  # price только для вывода


# sales/serializers.py - исправленный TransactionSerializer

# class TransactionSerializer(serializers.ModelSerializer):
#     items = TransactionItemSerializer(many=True)
#     customer = serializers.PrimaryKeyRelatedField(
#         queryset=Customer.objects.all(), required=False, allow_null=True
#     )
#     new_customer = serializers.DictField(
#         child=serializers.CharField(), required=False
#     )
#     cashier_name = serializers.CharField(source='cashier.username', read_only=True)
#     customer_name = serializers.CharField(source='customer.full_name', read_only=True)
#     store_name = serializers.CharField(source='store.name', read_only=True)

#     class Meta:
#         model = Transaction
#         fields = [
#             'id', 'cashier', 'cashier_name', 'total_amount',
#             'payment_method', 'status', 'customer', 'customer_name',
#             'new_customer', 'items', 'created_at', 'store_name'
#         ]
#         read_only_fields = ['id', 'cashier', 'cashier_name', 'total_amount', 'created_at', 'store_name']

#     def validate(self, data):
#         items = data.get('items', [])
#         customer = data.get('customer')
#         new_customer = data.get('new_customer')
#         payment_method = data.get('payment_method', 'cash')

#         if not items:
#             raise serializers.ValidationError(
#                 {"items": _("Должен быть хотя бы один товар")}
#             )

#         if payment_method == 'debt' and not (customer or new_customer):
#             raise serializers.ValidationError(
#                 {"error": _("Для оплаты в долг требуется customer_id или new_customer")}
#             )

#         if new_customer:
#             if not new_customer.get('full_name') or not new_customer.get('phone'):
#                 raise serializers.ValidationError(
#                     {"new_customer": _("Поля full_name и phone обязательны")}
#                 )

#         # Получаем текущий магазин из контекста
#         request = self.context.get('request')
#         current_store = None

#         if request and hasattr(request.user, 'current_store'):
#             current_store = request.user.current_store
#         else:
#             # Пытаемся получить из JWT
#             from rest_framework_simplejwt.tokens import AccessToken
#             auth_header = request.META.get('HTTP_AUTHORIZATION', '')
#             if auth_header.startswith('Bearer '):
#                 try:
#                     token = auth_header.split(' ')[1]
#                     decoded_token = AccessToken(token)
#                     store_id = decoded_token.get('store_id')
#                     if store_id:
#                         from stores.models import Store
#                         current_store = Store.objects.filter(id=store_id).first()
#                 except:
#                     current_store = None

#         # Проверяем доступность товаров в текущем магазине
#         total_amount = 0
#         for item in items:
#             product = item['product']
#             quantity = item['quantity']

#             # Проверяем что товар принадлежит текущему магазину
#             if current_store and hasattr(product, 'store'):
#                 if product.store != current_store:
#                     raise serializers.ValidationError(
#                         {"items": _(f"Товар {product.name} не принадлежит текущему магазину")}
#                     )

#             # Проверяем наличие на складе
#             if not hasattr(product, 'stock'):
#                 raise serializers.ValidationError(
#                     {"items": _(f"У товара {product.name} нет информации о складе")}
#                 )

#             if product.stock.quantity < quantity:
#                 raise serializers.ValidationError(
#                     {"items": _(f"Недостаточно товара {product.name} на складе. Доступно: {product.stock.quantity}")}
#                 )

#             total_amount += product.sale_price * quantity

#         data['total_amount'] = total_amount
#         return data

#     def create(self, validated_data):
#         items_data = validated_data.pop('items')
#         customer = validated_data.pop('customer', None)
#         new_customer = validated_data.pop('new_customer', None)

#         # ✅ ИСПРАВЛЕНИЕ: Убираем 'cashier' из validated_data
#         validated_data.pop('cashier', None)

#         # Получаем пользователя и магазин из контекста
#         request = self.context['request']
#         user = request.user

#         # Магазин должен быть установлен через perform_create в ViewSet
#         # Но на всякий случай проверяем
#         if 'store' not in validated_data:
#             if hasattr(user, 'current_store') and user.current_store:
#                 validated_data['store'] = user.current_store
#             else:
#                 raise serializers.ValidationError(
#                     {"error": "Не удалось определить текущий магазин"}
#                 )

#         # Обрабатываем нового покупателя
#         if new_customer:
#             phone = new_customer['phone']
#             # Ищем покупателя по телефону в текущем магазине
#             customer, created = Customer.objects.get_or_create(
#                 phone=phone,
#                 store=validated_data['store'],
#                 defaults={'full_name': new_customer['full_name']}
#             )
#             if created:
#                 logger.info(f"Created new customer: {customer.full_name} in store {validated_data['store'].name}")

#         # ✅ ИСПРАВЛЕНИЕ: Создаем транзакцию с явным указанием cashier
#         transaction = Transaction.objects.create(
#             cashier=user,  # ← Явно указываем cashier
#             customer=customer,
#             **validated_data  # ← Теперь не содержит cashier
#         )
#         logger.info(f"Transaction #{transaction.id} created in store {transaction.store.name}")

#         # Создаем элементы транзакции с привязкой к магазину
#         for item_data in items_data:
#             product = item_data['product']
#             quantity = item_data['quantity']
#             price = item_data.get('price', product.sale_price)

#             TransactionItem.objects.create(
#                 transaction=transaction,
#                 product=product,
#                 quantity=quantity,
#                 price=price,
#                 store=transaction.store  # Явно указываем store
#             )
#             logger.info(
#                 f"Transaction item created: Product {product.name}, Quantity: {quantity}, Store: {transaction.store.name}"
#             )

#         # Обрабатываем продажу
#         try:
#             transaction.process_sale()
#             logger.info(f"Transaction #{transaction.id} processed successfully. Total: {transaction.total_amount}")
#         except Exception as e:
#             logger.error(f"Error processing transaction #{transaction.id}: {str(e)}")
#             # Откатываем транзакцию
#             transaction.status = 'failed'
#             transaction.save()
#             raise serializers.ValidationError(
#                 {"error": f"Ошибка обработки продажи: {str(e)}"}
#             )

#         return transaction

#     def to_representation(self, instance):
#         """Добавляем дополнительную информацию при чтении"""
#         data = super().to_representation(instance)

#         # Добавляем информацию о магазине
#         if instance.store:
#             data['store'] = {
#                 'id': str(instance.store.id),
#                 'name': instance.store.name
#             }

#         # Добавляем детали товаров
#         items_detail = []
#         for item in instance.items.all():
#             items_detail.append({
#                 'product_id': item.product.id,
#                 'product_name': item.product.name,
#                 'quantity': item.quantity,
#                 'price': str(item.price),
#                 'subtotal': str(item.quantity * item.price)
#             })
#         data['items_detail'] = items_detail

#         return data

class TransactionSerializer(serializers.ModelSerializer):
    items = TransactionItemSerializer(many=True)
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
    new_customer = serializers.DictField(
        child=serializers.CharField(), required=False
    )
    cashier_name = serializers.CharField(source='cashier.username', read_only=True)
    customer_name = serializers.CharField(source='customer.full_name', read_only=True)
    store_name = serializers.CharField(source='store.name', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'cashier', 'cashier_name', 'total_amount',
            'payment_method', 'status', 'customer', 'customer_name',
            'new_customer', 'items', 'created_at', 'store_name'
        ]
        read_only_fields = ['id', 'cashier', 'cashier_name', 'total_amount', 'created_at', 'store_name']

    def validate(self, data):
        """
        Валидация с автоматическим расчетом цены из БД
        """
        items = data.get('items', [])
        customer = data.get('customer')
        new_customer = data.get('new_customer')
        payment_method = data.get('payment_method', 'cash')

        if not items:
            raise serializers.ValidationError(
                {"items": _("Должен быть хотя бы один товар")}
            )

        if payment_method == 'debt' and not (customer or new_customer):
            raise serializers.ValidationError(
                {"error": _("Для оплаты в долг требуется customer_id или new_customer")}
            )

        if new_customer:
            if not new_customer.get('full_name') or not new_customer.get('phone'):
                raise serializers.ValidationError(
                    {"new_customer": _("Поля full_name и phone обязательны")}
                )

        # Получаем текущий магазин
        request = self.context.get('request')
        current_store = None

        if request and hasattr(request.user, 'current_store'):
            current_store = request.user.current_store
        else:
            # Пытаемся получить из JWT
            from rest_framework_simplejwt.tokens import AccessToken
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                try:
                    token = auth_header.split(' ')[1]
                    decoded_token = AccessToken(token)
                    store_id = decoded_token.get('store_id')
                    if store_id:
                        from stores.models import Store
                        current_store = Store.objects.filter(id=store_id).first()
                except:
                    current_store = None

        # ✅ ГЛАВНОЕ ИЗМЕНЕНИЕ: Рассчитываем сумму ТОЛЬКО из цен в БД
        total_amount = 0
        for item in items:
            product = item['product']
            quantity = item['quantity']

            # ✅ НЕ ПРИНИМАЕМ цену с фронта - ВСЕГДА берем из товара
            # Даже если фронт попытается передать цену, мы её игнорируем
            item.pop('price', None)  # Удаляем если вдруг пришла

            # Берем актуальную цену из базы данных
            actual_price = product.sale_price

            if actual_price <= 0:
                raise serializers.ValidationError(
                    {"items": _(f"У товара {product.name} некорректная цена в базе данных: {actual_price}")}
                )

            logger.info(f"Using price from DB for {product.name}: {actual_price}")

            # Проверяем принадлежность к магазину
            if current_store and hasattr(product, 'store'):
                if product.store != current_store:
                    raise serializers.ValidationError(
                        {"items": _(f"Товар {product.name} не принадлежит текущему магазину")}
                    )

            # Проверяем наличие на складе
            if not hasattr(product, 'stock'):
                raise serializers.ValidationError(
                    {"items": _(f"У товара {product.name} нет информации о складе")}
                )

            if product.stock.quantity < quantity:
                raise serializers.ValidationError(
                    {"items": _(f"Недостаточно товара {product.name} на складе. Доступно: {product.stock.quantity}")}
                )

            # Считаем общую сумму ТОЛЬКО с ценой из БД
            total_amount += actual_price * quantity

        data['total_amount'] = total_amount
        logger.info(f"Total amount calculated from DB prices: {total_amount}")
        return data

    def create(self, validated_data):
        """
        Создание транзакции с ценами ТОЛЬКО из БД
        """
        items_data = validated_data.pop('items')
        customer = validated_data.pop('customer', None)
        new_customer = validated_data.pop('new_customer', None)

        # Убираем 'cashier' из validated_data
        validated_data.pop('cashier', None)

        # Получаем пользователя и магазин
        request = self.context['request']
        user = request.user

        # Проверяем магазин
        if 'store' not in validated_data:
            if hasattr(user, 'current_store') and user.current_store:
                validated_data['store'] = user.current_store
            else:
                raise serializers.ValidationError(
                    {"error": "Не удалось определить текущий магазин"}
                )

        # Обрабатываем нового покупателя
        if new_customer:
            phone = new_customer['phone']
            customer, created = Customer.objects.get_or_create(
                phone=phone,
                store=validated_data['store'],
                defaults={'full_name': new_customer['full_name']}
            )
            if created:
                logger.info(f"Created new customer: {customer.full_name}")

        # Создаем транзакцию
        transaction = Transaction.objects.create(
            cashier=user,
            customer=customer,
            **validated_data
        )
        logger.info(f"Transaction #{transaction.id} created in store {transaction.store.name}")

        # ✅ Создаем элементы транзакции с ценами ТОЛЬКО из БД
        for item_data in items_data:
            product = item_data['product']
            quantity = item_data['quantity']

            # ✅ ВСЕГДА берем цену из товара в БД
            price_from_db = product.sale_price

            # Дополнительная проверка
            if price_from_db <= 0:
                logger.error(f"Invalid price in DB for product {product.name}: {price_from_db}")
                raise serializers.ValidationError(
                    {"error": f"Некорректная цена товара {product.name} в базе данных"}
                )

            TransactionItem.objects.create(
                transaction=transaction,
                product=product,
                quantity=quantity,
                price=price_from_db,  # ← ТОЛЬКО цена из БД!
                store=transaction.store
            )
            logger.info(
                f"Transaction item created: {product.name} x{quantity} @ {price_from_db} "
                f"(price from DB)"
            )

        # Обрабатываем продажу
        try:
            transaction.process_sale()
            logger.info(f"Transaction #{transaction.id} processed. Total: {transaction.total_amount}")
        except Exception as e:
            logger.error(f"Error processing transaction #{transaction.id}: {str(e)}")
            transaction.status = 'failed'
            transaction.save()
            raise serializers.ValidationError(
                {"error": f"Ошибка обработки продажи: {str(e)}"}
            )

        return transaction

    def to_representation(self, instance):
        """
        При выводе показываем детальную информацию
        """
        data = super().to_representation(instance)

        # Добавляем информацию о магазине
        if instance.store:
            data['store'] = {
                'id': str(instance.store.id),
                'name': instance.store.name
            }

        # Добавляем детали товаров с ценами
        items_detail = []
        for item in instance.items.all():
            items_detail.append({
                'product_id': item.product.id,
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': str(item.price),  # Цена которая была сохранена (из БД)
                'subtotal': str(item.quantity * item.price)
            })
        data['items_detail'] = items_detail

        return data


# Остальные сериализаторы остаются без изменений
class FilteredTransactionHistorySerializer(serializers.ModelSerializer):
    """
    Сериализатор с фильтрацией - возвращает только валидные записи
    """
    parsed_details = serializers.SerializerMethodField()

    class Meta:
        model = TransactionHistory
        fields = ['id', 'transaction', 'action', 'parsed_details', 'created_at']

    def get_parsed_details(self, obj):
        try:
            details = json.loads(obj.details)

            # Возвращаем только если есть обязательные поля
            if (details.get('total_amount') and
                details.get('items') and
                len(details.get('items', [])) > 0):
                return details

            return None  # Если данные неполные

        except json.JSONDecodeError:
            return None

# class FilteredTransactionHistorySerializer(serializers.ModelSerializer):
#     """
#     Сериализатор с фильтрацией - возвращает только валидные записи
#     """
#     parsed_details = serializers.SerializerMethodField()

#     class Meta:
#         model = TransactionHistory
#         fields = ['id', 'transaction', 'action', 'parsed_details', 'created_at']

#     def get_parsed_details(self, obj):
#         try:
#             details = json.loads(obj.details)

#             # Возвращаем только если есть обязательные поля
#             if (details.get('total_amount') and
#                 details.get('items') and
#                 len(details.get('items', [])) > 0):
#                 return details

#             return None  # Если данные неполные

#         except json.JSONDecodeError:
#             return None

    # def to_representation(self, instance):
    #     """
    #     Переопределяем для исключения записей с пустыми parsed_details
    #     """
    #     data = super().to_representation(instance)

    #     # Если parsed_details пустые, возвращаем None (исключаем из результата)
    #     if not data.get('parsed_details'):
    #         return None

    #     return data

class CashierAggregateSerializer(serializers.Serializer):
    cashier_id = serializers.IntegerField()
    cashier_name = serializers.CharField()
    total_quantity = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)