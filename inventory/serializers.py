# inventory/serializers.py
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from drf_yasg.utils import swagger_serializer_method

from .models import (Product, ProductCategory, Stock,
                     ProductBatch, AttributeType,
                     AttributeValue, ProductAttribute,
                     SizeChart, SizeInfo
                     )
from users.serializers import UserSerializer



class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['created_at']
        extra_kwargs = {'name': {'trim_whitespace': True}}
        ref_name = 'ProductCategorySerializerInventory'

    def validate_name(self, value):
        value = value.strip()
        if ProductCategory.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError(
                _("Категория с названием '%(name)s' уже существует") % {'name': value},
                code='duplicate_category'
            )
        return value

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

class SizeInfoSerializer(serializers.ModelSerializer):
    size = serializers.CharField()

    class Meta:
        model = SizeInfo
        fields = ['id','size', 'chest', 'waist', 'length']
        read_only_fields = ['id']
        swagger_schema_fields = {
            'example': {
                'size': 'XXL',
                'chest': 100,
                'waist': 80,
                'length': 70
            }
        }


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



class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    size = SizeInfoSerializer(read_only=True)  # Убираем many=True
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
        allow_null=True  # Разрешаем null, так как size может быть пустым
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
            'barcode': {
                'required': False,
                'allow_blank': True
            }
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

        if Product.objects.filter(barcode=value) \
           .exclude(pk=self.instance.pk if self.instance else None) \
           .exists():
            raise serializers.ValidationError(
                _("Товар с таким штрихкодом уже существует"),
                code='duplicate_barcode'
            )

        return value

    def create(self, validated_data):
        """
        Создание товара с правильной обработкой размера
        """
        validated_data.pop('created_by', None)  # Убираем created_by из validated_data
        size = validated_data.pop('size', None)  # Извлекаем размер

        user = self.context['request'].user

        # Создаем товар БЕЗ размера
        product = Product.objects.create(created_by=user, **validated_data)

        # Устанавливаем размер ПОСЛЕ создания
        if size:
            product.size = size
            product.save()
            print(f"DEBUG: Размер {size} установлен для товара {product.name}")  # Отладка
        else:
            print(f"DEBUG: Размер не передан для товара {product.name}")  # Отладка

        return product


    def update(self, instance, validated_data):
        size = validated_data.pop('size', None)
        product = super().update(instance, validated_data)
        if size is not None:
            product.size = size  # Прямое присваивание для ForeignKey
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
    unit = serializers.CharField(max_length=50)
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

    def save(self, **kwargs):
        created_by = kwargs.get('created_by')
        if not created_by:
            raise serializers.ValidationError("created_by is required")

        validated_data = self.validated_data
        batch_info = validated_data.get('batch_info', [])

        created_products = []

        # Извлекаем уникальные размеры из batch_info
        size_ids = list(set(batch['size_id'] for batch in batch_info))

        if not size_ids:
            raise serializers.ValidationError("Необходимо указать хотя бы один размер в batch_info")

        for size_id in size_ids:
            try:
                size_instance = SizeInfo.objects.get(id=size_id)
                product_name = f"{validated_data['name']} - {size_instance.size}"
                unique_barcode = self.generate_unique_barcode()

                # Создаем товар
                product = Product.objects.create(
                    name=product_name,
                    barcode=unique_barcode,
                    created_by=created_by,
                    category=validated_data['category'],
                    sale_price=validated_data['sale_price'],
                    unit=validated_data['unit'],
                    size=size_instance
                )

                # Создаем batch для этого размера
                batch_for_size = next((b for b in batch_info if b['size_id'] == size_id), None)
                if batch_for_size:
                    ProductBatch.objects.create(
                        product=product,
                        quantity=batch_for_size['quantity'],
                        purchase_price=batch_for_size['purchase_price'],
                        supplier=batch_for_size['supplier'],
                        expiration_date=batch_for_size.get('expiration_date')
                    )

                product.generate_label()
                created_products.append(product)

            except SizeInfo.DoesNotExist:
                raise serializers.ValidationError(f"Размер с ID {size_id} не найден")

        return created_products

    def generate_unique_barcode(self):
        import uuid
        return str(uuid.uuid4().int)[:12]
