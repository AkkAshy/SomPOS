# inventory/serializers.py - ОБНОВЛЕННАЯ ВЕРСИЯ
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from drf_yasg.utils import swagger_serializer_method
from django.db import transaction
from decimal import Decimal

from .models import (Product, ProductCategory, Stock,
                     ProductBatch, AttributeType,
                     AttributeValue, ProductAttribute,
                     SizeChart, SizeInfo, CustomUnit
                     )
from users.serializers import UserSerializer
import logging
from stores.mixins import StoreSerializerMixin

logger = logging.getLogger('inventory')


class CustomUnitSerializer(StoreSerializerMixin, serializers.ModelSerializer):
    """
    Сериализатор для пользовательских единиц измерения
    """
    class Meta:
        model = CustomUnit
        fields = [
            'id', 'name', 'short_name', 'allow_decimal', 
            'min_quantity', 'step'
        ]
        read_only_fields = ['id']

    def validate_short_name(self, value):
        """Проверяем уникальность сокращения в рамках магазина"""
        value = value.strip()
        request = self.context.get('request')
        
        if request and hasattr(request.user, 'current_store') and request.user.current_store:
            current_store = request.user.current_store
            
            existing_query = CustomUnit.objects.filter(
                store=current_store,
                short_name__iexact=value
            )
            
            if self.instance:
                existing_query = existing_query.exclude(pk=self.instance.pk)
            
            if existing_query.exists():
                raise serializers.ValidationError(
                    f"Единица с сокращением '{value}' уже существует в вашем магазине"
                )
        
        return value


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ['id', 'name', 'created_at', 'is_deleted']
        read_only_fields = ['created_at', 'is_deleted']
        extra_kwargs = {'name': {'trim_whitespace': True}}
        ref_name = 'ProductCategorySerializerInventory'

    def validate_name(self, value):
        value = value.strip()
        request = self.context.get('request')

        if not request:
            if ProductCategory.objects.filter(name__iexact=value).exists():
                raise serializers.ValidationError(
                    _("Категория с названием '%(name)s' уже существует") % {'name': value},
                    code='duplicate_category'
                )
            return value

        # Получаем текущий магазин
        current_store = None

        if hasattr(request.user, 'current_store') and request.user.current_store:
            current_store = request.user.current_store

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

        # Проверяем уникальность только среди АКТИВНЫХ категорий
        existing_query = ProductCategory.objects.filter(
            store=current_store,
            name__iexact=value
        )

        if self.instance:
            existing_query = existing_query.exclude(pk=self.instance.pk)

        if existing_query.exists():
            deleted_category = ProductCategory.all_objects.filter(
                store=current_store,
                name__iexact=value,
                deleted_at__isnull=False
            ).first()

            if deleted_category:
                raise serializers.ValidationError(
                    _("Категория с названием '%(name)s' была удалена. Восстановите её или выберите другое название") % {'name': value},
                    code='category_was_deleted'
                )
            else:
                raise serializers.ValidationError(
                    _("Категория с названием '%(name)s' уже существует в вашем магазине") % {'name': value},
                    code='duplicate_category_in_store'
                )

        return value

    def update(self, instance, validated_data):
        """При обновлении проверяем что категория принадлежит текущему магазину и не удалена"""
        request = self.context.get('request')
        if request and hasattr(request.user, 'current_store') and request.user.current_store:
            if instance.store != request.user.current_store:
                raise serializers.ValidationError(
                    _("Вы не можете редактировать категории другого магазина"),
                    code='wrong_store'
                )

            if instance.is_deleted:
                raise serializers.ValidationError(
                    _("Нельзя редактировать удаленную категорию"),
                    code='category_deleted'
                )

        return super().update(instance, validated_data)


class SizeInfoSerializer(StoreSerializerMixin, serializers.ModelSerializer):
    """
    ОБНОВЛЕННЫЙ сериализатор для размерной информации с новыми полями
    """
    size = serializers.CharField()
    store_name = serializers.CharField(source='store.name', read_only=True)
    full_description = serializers.CharField(read_only=True)

    class Meta:
        model = SizeInfo
        fields = [
            'id', 'size', 'dimension1', 'dimension2', 'dimension3',
            'dimension1_label', 'dimension2_label', 'dimension3_label',
            'description', 'sort_order', 'store_name', 'is_deleted',
            'full_description'
        ]
        read_only_fields = ['id', 'store_name', 'is_deleted', 'full_description']
        swagger_schema_fields = {
            'example': {
                'size': '1/2"',
                'dimension1': 15.0,
                'dimension2': 20.0,
                'dimension3': 2.5,
                'dimension1_label': 'Внутр. диаметр',
                'dimension2_label': 'Внешн. диаметр',
                'dimension3_label': 'Толщина стенки',
                'description': 'Труба полипропиленовая',
                'sort_order': 0
            }
        }

    def validate_size(self, value):
        """Валидация размера"""
        if not value or not value.strip():
            raise serializers.ValidationError("Размер не может быть пустым")

        value = value.strip()

        if len(value) > 50:
            raise serializers.ValidationError("Размер не может быть длиннее 50 символов")

        return value

    def validate(self, attrs):
        """Комплексная валидация с учетом soft delete"""
        attrs = super().validate(attrs)
        request = self.context.get('request')

        if not request:
            return attrs

        # Получаем текущий магазин
        current_store = None

        if hasattr(request.user, 'current_store') and request.user.current_store:
            current_store = request.user.current_store

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

            if not current_store:
                from stores.models import StoreEmployee
                store_membership = StoreEmployee.objects.filter(
                    user=request.user,
                    is_active=True
                ).select_related('store').first()

                if store_membership:
                    current_store = store_membership.store

        if not current_store:
            raise serializers.ValidationError("Не удалось определить текущий магазин")

        size = attrs.get('size')

        # Проверяем уникальность только среди АКТИВНЫХ размеров
        existing_query = SizeInfo.objects.filter(
            store=current_store,
            size=size
        )

        if self.instance:
            existing_query = existing_query.exclude(pk=self.instance.pk)

        if existing_query.exists():
            deleted_size = SizeInfo.all_objects.filter(
                store=current_store,
                size=size,
                deleted_at__isnull=False
            ).first()

            if deleted_size:
                raise serializers.ValidationError(
                    f"Размер '{size}' был удален. Восстановите его или выберите другое название"
                )
            else:
                raise serializers.ValidationError(
                    f"Размер '{size}' уже существует в этом магазине"
                )

        return attrs

    def update(self, instance, validated_data):
        """При обновлении проверяем что размер принадлежит текущему магазину и не удален"""
        request = self.context.get('request')
        if request and hasattr(request.user, 'current_store') and request.user.current_store:
            if instance.store != request.user.current_store:
                raise serializers.ValidationError(
                    "Вы не можете редактировать размеры другого магазина"
                )

            if instance.is_deleted:
                raise serializers.ValidationError(
                    "Нельзя редактировать удаленный размер"
                )

        return super().update(instance, validated_data)


# Остальные сериализаторы остаются без изменений
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


class SizeChartSerializer(serializers.ModelSerializer):
    class Meta:
        model = SizeChart
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['created_at']



class ProductBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    size_info = serializers.SerializerMethodField()

    class Meta:
        model = ProductBatch
        fields = [
            'id', 'product', 'product_name', 'quantity', 'purchase_price',
            'size_info', 'supplier', 'expiration_date', 'created_at'
        ]

    def get_size_info(self, obj):
        """Возвращает информацию о размере"""
        if obj.size:
            return {
                'id': obj.size.id,
                'size': obj.size.size,
                'dimension1': float(obj.size.dimension1) if obj.size.dimension1 else None,
                'dimension2': float(obj.size.dimension2) if obj.size.dimension2 else None,
                'dimension3': float(obj.size.dimension3) if obj.size.dimension3 else None,
                'dimension1_label': obj.size.dimension1_label,
                'dimension2_label': obj.size.dimension2_label,
                'dimension3_label': obj.size.dimension3_label,
                'full_description': obj.size.full_description
            }
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
    """
    ОБНОВЛЕННЫЙ сериализатор для товаров с новой системой единиц измерения
    """
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    # Размеры и варианты
    default_size = SizeInfoSerializer(read_only=True)
    available_sizes = SizeInfoSerializer(many=True, read_only=True)
    default_size_id = serializers.PrimaryKeyRelatedField(
        source='default_size',
        queryset=SizeInfo.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    available_size_ids = serializers.PrimaryKeyRelatedField(
        source='available_sizes',
        queryset=SizeInfo.objects.all(),
        many=True,
        write_only=True,
        required=False
    )
    
    # Единицы измерения
    custom_unit = CustomUnitSerializer(read_only=True)
    custom_unit_id = serializers.PrimaryKeyRelatedField(
        source='custom_unit',
        queryset=CustomUnit.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )
    unit_display = serializers.CharField(read_only=True)
    
    # Остатки и партии
    current_stock = serializers.IntegerField(
        source='stock.quantity',
        read_only=True,
        help_text=_('Текущий остаток на складе')
    )
    batches = ProductBatchSerializer(many=True, read_only=True)
    
    # Ценовая информация
    price_info = serializers.JSONField(read_only=True)
    
    # Размерная информация
    sizes_info = serializers.JSONField(read_only=True)
    
    # Метаданные
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'barcode', 'category', 'category_name',
            'unit_type', 'custom_unit', 'custom_unit_id', 'unit_display',
            'override_min_quantity', 'override_step',
            'sale_price', 'price_info',
            'has_sizes', 'default_size', 'default_size_id', 
            'available_sizes', 'available_size_ids', 'sizes_info',
            'attributes', 'created_at', 'created_by',
            'current_stock', 'batches', 'image_label',
            'is_deleted', 'deleted_at'
        ]
        read_only_fields = [
            'created_at', 'current_stock', 'created_by', 'unit_display',
            'price_info', 'sizes_info', 'is_deleted', 'deleted_at'
        ]
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

        # Проверяем уникальность с учетом магазина
        request = self.context.get('request')
        if request and hasattr(request.user, 'current_store') and request.user.current_store:
            existing_query = Product.objects.filter(
                store=request.user.current_store,
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

    def validate(self, attrs):
        """Валидация единиц измерения"""
        unit_type = attrs.get('unit_type')
        custom_unit = attrs.get('custom_unit')

        # Должна быть указана единица измерения
        if not unit_type and not custom_unit:
            raise serializers.ValidationError(
                "Укажите единицу измерения (системную или пользовательскую)"
            )

        if unit_type and custom_unit:
            raise serializers.ValidationError(
                "Выберите либо системную, либо пользовательскую единицу"
            )

        return attrs

    def create(self, validated_data):
        """Создание товара с обработкой размеров"""
        # Извлекаем размеры
        default_size = validated_data.pop('default_size', None)
        available_sizes = validated_data.pop('available_sizes', [])

        # Создаем товар
        product = Product.objects.create(**validated_data)

        # обработка размеров
        default_size = validated_data.get('default_size')
        available_sizes = validated_data.get('available_sizes')

        if default_size:
            product.default_size = default_size
        if available_sizes:
            product.available_sizes.set(available_sizes)

        product.save()
        return product


    def update(self, instance, validated_data):
        """Обновление товара с обработкой размеров"""
        # Извлекаем размеры
        default_size = validated_data.pop('default_size', None)
        available_sizes = validated_data.pop('available_sizes', None)

        # Обновляем основные поля
        product = super().update(instance, validated_data)

        # Обновляем размеры
        if default_size is not None:
            product.default_size = default_size

        if available_sizes is not None:
            product.available_sizes.set(available_sizes)

        product.save()
        return product


class StockSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True, allow_null=True)
    unit_display = serializers.CharField(source='product.unit_display', read_only=True)

    class Meta:
        model = Stock
        fields = [
            'product', 'product_name', 'product_barcode', 'unit_display',
            'quantity', 'updated_at'
        ]
        read_only_fields = ['updated_at', 'product_name', 'product_barcode', 'unit_display']

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError(
                _("Количество не может быть отрицательным"),
                code='negative_quantity'
            )
        return value


class ProductMultiSizeCreateSerializer(serializers.Serializer):
    """
    ОБНОВЛЕННЫЙ сериализатор для создания товаров с размерами
    """
    name = serializers.CharField(max_length=255)
    category = serializers.PrimaryKeyRelatedField(queryset=ProductCategory.objects.all())
    sale_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit_type = serializers.ChoiceField(
        choices=Product.SYSTEM_UNITS,
        required=False,
        allow_null=True
    )
    custom_unit_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUnit.objects.all(),
        required=False,
        allow_null=True
    )
    batch_info = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True
    )

    def validate(self, attrs):
        """Валидация единиц измерения"""
        unit_type = attrs.get('unit_type')
        custom_unit_id = attrs.get('custom_unit_id')

        # Должна быть указана единица измерения
        if not unit_type and not custom_unit_id:
            raise serializers.ValidationError(
                "Укажите единицу измерения (системную или пользовательскую)"
            )

        if unit_type and custom_unit_id:
            raise serializers.ValidationError(
                "Выберите либо системную, либо пользовательскую единицу"
            )

        return attrs

    def validate_batch_info(self, value):
        """Валидация batch_info"""
        if not value:
            return value

        for batch in value:
            required_fields = ['size_id', 'quantity', 'purchase_price', 'supplier']
            for field in required_fields:
                if field not in batch:
                    raise serializers.ValidationError(f"Поле '{field}' обязательно для batch_info")

            try:
                SizeInfo.objects.get(id=batch['size_id'])
            except SizeInfo.DoesNotExist:
                raise serializers.ValidationError(f"Размер с ID {batch['size_id']} не найден")

            if batch['quantity'] <= 0:
                raise serializers.ValidationError("Количество должно быть больше нуля")

        return value

    def create(self, validated_data):
        """Создание множественных товаров с новой системой единиц"""
        store = validated_data.get('store')
        created_by = validated_data.get('created_by')

        if not store:
            raise serializers.ValidationError("Store is required")
        if not created_by:
            raise serializers.ValidationError("created_by is required")

        batch_info = validated_data.get('batch_info', [])

        if not batch_info:
            raise serializers.ValidationError("batch_info с размерами обязателен")

        created_products = []
        size_ids = list(set(batch['size_id'] for batch in batch_info))

        try:
            with transaction.atomic():
                for size_id in size_ids:
                    try:
                        size_instance = SizeInfo.objects.get(id=size_id)
                        product_name = f"{validated_data['name']} - {size_instance.size}"
                        unique_barcode = self.generate_unique_barcode(store)

                        # Подготавливаем данные для создания товара
                        product_data = {
                            'name': product_name,
                            'barcode': unique_barcode,
                            'created_by': created_by,
                            'category': validated_data['category'],
                            'sale_price': validated_data['sale_price'],
                            'store': store,
                            'has_sizes': True,
                            'default_size': size_instance
                        }

                        # Устанавливаем единицу измерения
                        if validated_data.get('unit_type'):
                            product_data['unit_type'] = validated_data['unit_type']
                        elif validated_data.get('custom_unit_id'):
                            product_data['custom_unit'] = validated_data['custom_unit_id']

                        # Создаем товар
                        product = Product.objects.create(**product_data)

                        # Создаем Stock
                        Stock.objects.get_or_create(
                            product=product,
                            defaults={'store': store, 'quantity': 0}
                        )

                        # Создаем batch
                        batch_for_size = next((b for b in batch_info if b['size_id'] == size_id), None)
                        if batch_for_size:
                            batch = ProductBatch.objects.create(
                                product=product,
                                store=store,
                                size=size_instance,
                                quantity=batch_for_size['quantity'],
                                purchase_price=batch_for_size['purchase_price'],
                                supplier=batch_for_size['supplier'],
                                expiration_date=batch_for_size.get('expiration_date')
                            )

                            product.stock.update_quantity()

                        created_products.append(product)

                    except SizeInfo.DoesNotExist:
                        logger.error(f"Size with ID {size_id} not found")
                        raise serializers.ValidationError(f"Размер с ID {size_id} не найден")

        except Exception as e:
            logger.error(f"Transaction failed in multi-size creation: {str(e)}")
            raise

        return created_products

    def generate_unique_barcode(self, store):
        """Генерирует уникальный штрих-код для конкретного магазина"""
        import uuid
        import random
        import time

        max_attempts = 100
        attempts = 0

        while attempts < max_attempts:
            timestamp = str(int(time.time()))[-6:]
            random_part = str(random.randint(100000, 999999))
            barcode_code = timestamp + random_part
            checksum = self._calculate_ean13_checksum(barcode_code)
            full_barcode = barcode_code + checksum

            if not Product.objects.filter(store=store, barcode=full_barcode).exists():
                return full_barcode

            attempts += 1

        return str(uuid.uuid4().int)[:12]

    def _calculate_ean13_checksum(self, digits):
        """Вычисляет контрольную цифру EAN-13"""
        weights = [1, 3] * 6
        total = sum(int(d) * w for d, w in zip(digits, weights))
        return str((10 - (total % 10)) % 10)