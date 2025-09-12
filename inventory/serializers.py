# inventory/serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from drf_yasg.utils import swagger_serializer_method
from django.db import transaction

from .models import (Product, ProductCategory, Stock,
                     ProductBatch, AttributeType,
                     AttributeValue, ProductAttribute,
                     SizeChart, SizeInfo
                     )
from users.serializers import UserSerializer
import logging
from stores.mixins import StoreSerializerMixin

logger = logging.getLogger('inventory')



class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['created_at']
        extra_kwargs = {'name': {'trim_whitespace': True}}
        ref_name = 'ProductCategorySerializerInventory'

    def validate_name(self, value):
        value = value.strip()

        # ✅ ИСПРАВЛЕНИЕ: Проверяем уникальность ТОЛЬКО в рамках текущего магазина
        request = self.context.get('request')

        if not request:
            # Если нет контекста запроса, используем глобальную проверку как fallback
            if ProductCategory.objects.filter(name__iexact=value).exists():
                raise serializers.ValidationError(
                    _("Категория с названием '%(name)s' уже существует") % {'name': value},
                    code='duplicate_category'
                )
            return value

        # Получаем текущий магазин из пользователя
        current_store = None

        # Способ 1: Из атрибута пользователя (установлено middleware)
        if hasattr(request.user, 'current_store') and request.user.current_store:
            current_store = request.user.current_store

        # Способ 2: Из JWT токена
        if not current_store:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                try:
                    from rest_framework_simplejwt.tokens import AccessToken
                    token = auth_header.split(' ')[1]
                    decoded_token = AccessToken(token)
                    store_id = decoded_token.get('store_id')

                    if store_id:
                        from stores.models import Store
                        current_store = Store.objects.filter(id=store_id).first()
                except Exception:
                    pass

        # Способ 3: Через StoreEmployee
        if not current_store:
            from stores.models import StoreEmployee
            store_membership = StoreEmployee.objects.filter(
                user=request.user,
                is_active=True
            ).select_related('store').first()

            if store_membership:
                current_store = store_membership.store

        if not current_store:
            raise serializers.ValidationError(
                _("Не удалось определить текущий магазин"),
                code='no_store'
            )

        # ✅ ГЛАВНОЕ ИСПРАВЛЕНИЕ: Проверяем уникальность только в ТЕКУЩЕМ магазине
        existing_query = ProductCategory.objects.filter(
            store=current_store,  # ← ФИЛЬТР ПО МАГАЗИНУ!
            name__iexact=value
        )

        # Если это обновление существующей категории, исключаем её из проверки
        if self.instance:
            existing_query = existing_query.exclude(pk=self.instance.pk)

        if existing_query.exists():
            raise serializers.ValidationError(
                _("Категория с названием '%(name)s' уже существует в вашем магазине") % {'name': value},
                code='duplicate_category_in_store'
            )

        return value

    # ✅ ИСПРАВЛЕНИЕ: Убираем кастомный create и используем стандартный
    # def create(self, validated_data):
    #     """
    #     При создании НЕ устанавливаем store здесь - это сделает StoreViewSetMixin.perform_create()
    #     """
    #     return ProductCategory(**validated_data)

    def update(self, instance, validated_data):
        """
        При обновлении проверяем что категория принадлежит текущему магазину
        """
        request = self.context.get('request')
        if request and hasattr(request.user, 'current_store') and request.user.current_store:
            if instance.store != request.user.current_store:
                raise serializers.ValidationError(
                    _("Вы не можете редактировать категории другого магазина"),
                    code='wrong_store'
                )

        return super().update(instance, validated_data)

############################################################# Атрибуты #############################################################
class AttributeValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeValue
        fields = ['id', 'attribute_type', 'value', 'slug']

class AttributeTypeSerializer(serializers.ModelSerializer):
    values = AttributeValueSerializer(many=True, read_only=True)

    class Meta:
        model = AttributeType
        fields = ['id', 'name', 'slug', 'is_filterable', 'values']

class ProductAttributeSerializer(serializers.ModelSerializer):
    attribute = AttributeValueSerializer(read_only=True)
    attribute_id = serializers.PrimaryKeyRelatedField(
        queryset=AttributeValue.objects.all(),
        source='attribute',
        write_only=True,
        help_text=_('ID значения атрибута')
    )

    class Meta:
        model = ProductAttribute
        fields = ['attribute', 'attribute_id']
############################################################# Атрибуты конец #############################################################


class SizeChartSerializer(serializers.ModelSerializer):
    class Meta:
        model = SizeChart
        fields = ['id', 'name', 'values']

class SizeInfoSerializer(StoreSerializerMixin, serializers.ModelSerializer):
    size = serializers.CharField()
    store_name = serializers.CharField(source='store.name', read_only=True)

    class Meta:
        model = SizeInfo
        fields = ['id', 'size', 'chest', 'waist', 'length', 'store_name']
        read_only_fields = ['id', 'store_name']
        swagger_schema_fields = {
            'example': {
                'size': 'XXL',
                'chest': 100,
                'waist': 80,
                'length': 70
            }
        }

    def validate_size(self, value):
        """Валидация размера"""
        if not value or not value.strip():
            raise serializers.ValidationError("Размер не может быть пустым")

        # Приводим к верхнему регистру для консистентности
        value = value.strip().upper()

        # Проверяем длину
        if len(value) > 50:
            raise serializers.ValidationError("Размер не может быть длиннее 50 символов")

        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context['request']
        store = getattr(request.user, 'store', None)  # или откуда у тебя магазин берётся
        size = attrs.get('size')

        if SizeInfo.objects.filter(store=store, size=size).exists():
            raise serializers.ValidationError(
                f"Размер '{size}' уже существует в этом магазине"
            )

        return attrs


############################################################## Продукты #############################################################

class ProductBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    size = serializers.SerializerMethodField()

    class Meta:
        model = ProductBatch
        fields = [
            'id',
            'product',
            'product_name',
            'quantity',
            'purchase_price',
            'size',
            'supplier',
            'expiration_date',
            'created_at'
        ]

    def get_size(self, obj):
        """Возвращает размер из поля size модели Product"""
        if obj.product.size:  # Проверяем, есть ли связанный размер
            return obj.product.size.size  # Возвращаем значение поля size из SizeInfo
        return None

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                _("Количество должно быть больше нуля"),
                code='invalid_quantity'
            )
        return value

    def validate(self, data):
        expiration_date = data.get('expiration_date')
        if expiration_date and expiration_date < timezone.now().date():
            raise serializers.ValidationError(
                {'expiration_date': _("Срок годности не может быть в прошлом")},
                code='expired_product'
            )
        return data



class ProductSerializer(StoreSerializerMixin, serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    size = SizeInfoSerializer(read_only=True)
    current_stock = serializers.IntegerField(
        source='stock.quantity',
        read_only=True,
        help_text=_('Текущий остаток на складе')
    )
    size_id = serializers.PrimaryKeyRelatedField(
        source='size',
        queryset=SizeInfo.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    unit = serializers.ChoiceField(
        choices=Product.UNIT_CHOICES,
        read_only=True,
        help_text=_('Единица измерения товара')
    )
    batches = ProductBatchSerializer(
        many=True,
        read_only=True,
        help_text=_('Партии товара')
    )
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'barcode',
            'category',
            'category_name',
            'sale_price',
            'created_at',
            'size',
            'size_id',
            'unit',
            'current_stock',
            'batches',
            'image_label',
            'created_by'
        ]
        read_only_fields = ['created_at', 'current_stock', 'created_by']
        extra_kwargs = {
            'name': {'trim_whitespace': True},
            'barcode': {'required': False, 'allow_blank': True},
        }

    def validate_sale_price(self, value):
        if value < 0:
            raise serializers.ValidationError(
                _("Цена не может быть отрицательной"),
                code='negative_price'
            )
        return round(value, 2)

    def validate_barcode(self, value):
        if not value:
            return value

        value = value.strip()
        if not value.isdigit():
            raise serializers.ValidationError(
                _("Штрихкод должен содержать только цифры"),
                code='invalid_barcode_format'
            )

        if len(value) > 100:
            raise serializers.ValidationError(
                _("Штрихкод не может быть длиннее 100 символов"),
                code='barcode_too_long'
            )

        # ✅ ИСПРАВЛЕНО: Проверяем уникальность с учетом магазина
        request = self.context.get('request')
        if request and hasattr(request.user, 'current_store') and request.user.current_store:
            existing_query = Product.objects.filter(
                store=request.user.current_store,  # ← Фильтр по магазину
                barcode=value
            )

            if self.instance:
                existing_query = existing_query.exclude(pk=self.instance.pk)

            if existing_query.exists():
                raise serializers.ValidationError(
                    _("Товар с таким штрихкодом уже существует в этом магазине"),
                    code='duplicate_barcode'
                )

        return value

    def create(self, validated_data):
        """
        ✅ ИСПРАВЛЕННОЕ создание товара - НЕ ТРОГАЕМ СИГНАЛЫ
        """
        size = validated_data.pop('size', None)

        # ✅ ВАЖНО: НЕ устанавливаем created_by здесь - это сделает StoreViewSetMixin
        # ✅ ВАЖНО: НЕ устанавливаем store здесь - это сделает StoreViewSetMixin

        # Создаем товар БЕЗ store и created_by - их установит миксин в perform_create
        product = Product(**validated_data)

        # НЕ СОХРАНЯЕМ ЕЩЕ! Пусть StoreViewSetMixin.perform_create сохранит с store
        return product

    def update(self, instance, validated_data):
        size = validated_data.pop('size', None)
        product = super().update(instance, validated_data)
        if size is not None:
            product.size = size
            product.save()
        return product

class StockSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source='product.name',
        read_only=True
    )

    product_barcode = serializers.CharField(
        source='product.barcode',
        read_only=True,
        allow_null=True
    )


    class Meta:
        model = Stock
        fields = [
            'product', 'product_name', 'product_barcode',
            'quantity', 'updated_at'
        ]
        read_only_fields = ['updated_at', 'product_name', 'product_barcode']
        swagger_schema_fields = {
            'example': {
                'product': 1,
                'quantity': 100
            }
        }

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError(
                _("Количество не может быть отрицательным"),
                code='negative_quantity'
            )
        return value


class ProductMultiSizeCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    category = serializers.PrimaryKeyRelatedField(queryset=ProductCategory.objects.all())
    sale_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit = serializers.CharField(max_length=50, default='piece')
    batch_info = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True
    )

    def validate_batch_info(self, value):
        """Валидация batch_info"""
        if not value:
            return value

        for batch in value:
            # Проверяем обязательные поля
            required_fields = ['size_id', 'quantity', 'purchase_price', 'supplier']
            for field in required_fields:
                if field not in batch:
                    raise serializers.ValidationError(f"Поле '{field}' обязательно для batch_info")

            # Проверяем что size_id существует
            try:
                SizeInfo.objects.get(id=batch['size_id'])
            except SizeInfo.DoesNotExist:
                raise serializers.ValidationError(f"Размер с ID {batch['size_id']} не найден")

            # Проверяем количество
            if batch['quantity'] <= 0:
                raise serializers.ValidationError("Количество должно быть больше нуля")

        return value

    def create(self, validated_data):
        """
        ✅ ИСПРАВЛЕННОЕ создание множественных товаров
        """
        # Извлекаем необходимые данные
        store = validated_data.get('store')  # Передается из view
        created_by = validated_data.get('created_by')  # Передается из view

        if not store:
            raise serializers.ValidationError("Store is required")
        if not created_by:
            raise serializers.ValidationError("created_by is required")

        batch_info = validated_data.get('batch_info', [])

        if not batch_info:
            raise serializers.ValidationError("batch_info с размерами обязателен")

        created_products = []

        # Извлекаем уникальные размеры из batch_info
        size_ids = list(set(batch['size_id'] for batch in batch_info))

        try:
            with transaction.atomic():
                for size_id in size_ids:
                    try:
                        # Получаем размер
                        size_instance = SizeInfo.objects.get(id=size_id)

                        # Создаем имя товара с размером
                        product_name = f"{validated_data['name']} - {size_instance.size}"

                        # Генерируем уникальный штрих-код
                        unique_barcode = self.generate_unique_barcode(store)

                        # ✅ Создаем товар СРАЗУ с store
                        product = Product.objects.create(
                            name=product_name,
                            barcode=unique_barcode,
                            created_by=created_by,
                            category=validated_data['category'],
                            sale_price=validated_data['sale_price'],
                            unit=validated_data.get('unit', 'piece'),
                            size=size_instance,
                            store=store  # ← ВАЖНО: устанавливаем store сразу
                        )

                        logger.info(f"✅ Multi-size product created: {product.name} in store {store.name}")

                        # ✅ Создаем Stock вручную с правильным store
                        Stock.objects.get_or_create(
                            product=product,
                            defaults={
                                'store': store,
                                'quantity': 0
                            }
                        )
                        logger.info(f"✅ Stock created for multi-size product: {product.name}")

                        # Создаем batch для этого размера
                        batch_for_size = next((b for b in batch_info if b['size_id'] == size_id), None)
                        if batch_for_size:
                            batch = ProductBatch.objects.create(
                                product=product,
                                store=store,  # ← ВАЖНО: устанавливаем store
                                quantity=batch_for_size['quantity'],
                                purchase_price=batch_for_size['purchase_price'],
                                supplier=batch_for_size['supplier'],
                                expiration_date=batch_for_size.get('expiration_date')
                            )
                            logger.info(f"✅ Batch created for multi-size product: {product.name}")

                            # Обновляем количество в Stock
                            product.stock.update_quantity()

                        # Генерируем этикетку
                        try:
                            product.generate_label()
                            logger.info(f"✅ Label generated for multi-size product: {product.name}")
                        except Exception as e:
                            logger.error(f"⚠️ Label generation failed for {product.name}: {str(e)}")

                        created_products.append(product)

                    except SizeInfo.DoesNotExist:
                        logger.error(f"❌ Size with ID {size_id} not found")
                        raise serializers.ValidationError(f"Размер с ID {size_id} не найден")
                    except Exception as e:
                        logger.error(f"❌ Error creating product for size {size_id}: {str(e)}")
                        raise

        except Exception as e:
            logger.error(f"❌ Transaction failed in multi-size creation: {str(e)}")
            raise

        logger.info(f"✅ Successfully created {len(created_products)} multi-size products")
        return created_products

    def generate_unique_barcode(self, store):
        """Генерирует уникальный штрих-код для конкретного магазина"""
        import uuid
        import random
        import time

        max_attempts = 100
        attempts = 0

        while attempts < max_attempts:
            # Генерируем на основе времени и случайных чисел
            timestamp = str(int(time.time()))[-6:]
            random_part = str(random.randint(100000, 999999))
            barcode_code = timestamp + random_part

            # Добавляем контрольную сумму
            checksum = self._calculate_ean13_checksum(barcode_code)
            full_barcode = barcode_code + checksum

            # Проверяем уникальность В ПРЕДЕЛАХ МАГАЗИНА
            if not Product.objects.filter(store=store, barcode=full_barcode).exists():
                return full_barcode

            attempts += 1

        # Fallback - используем UUID
        return str(uuid.uuid4().int)[:12]

    def _calculate_ean13_checksum(self, digits):
        """Вычисляет контрольную цифру EAN-13"""
        weights = [1, 3] * 6
        total = sum(int(d) * w for d, w in zip(digits, weights))
        return str((10 - (total % 10)) % 10)