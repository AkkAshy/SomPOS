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
        validated_data.pop('created_by', None)
        size = validated_data.pop('size', None)
        user = self.context['request'].user
        product = Product.objects.create(created_by=user, **validated_data)

        if size:
            product.size = size
            product.save()
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
    sale_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    unit = serializers.ChoiceField(choices=Product.UNIT_CHOICES, default='piece')

    # Список партий, каждая с уникальным размером
    batch_info = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        help_text="Список партий с размером и количеством"
    )

    def validate_name(self, value):
        return value.strip()

    def validate_sale_price(self, value):
        return round(value, 2)

    def validate(self, data):
        seen_sizes = set()
        for item in data['batch_info']:
            size_id = item.get('size_id')
            if not size_id:
                raise serializers.ValidationError("Каждая партия должна содержать size_id.")
            if size_id in seen_sizes:
                raise serializers.ValidationError(f"Размер с ID {size_id} указан дважды.")
            seen_sizes.add(size_id)
        return data

    def create(self, validated_data):
        batch_info = validated_data.pop('batch_info')
        base_name = validated_data.pop('name')
        created_products = []

        for info in batch_info:
            size = SizeInfo.objects.get(pk=info['size_id'])
            quantity = info['quantity']
            purchase_price = info.get('purchase_price')
            supplier = info.get('supplier')
            expiration_date = info.get('expiration_date')

            barcode = self._generate_unique_barcode()

            product = Product.objects.create(
                name=base_name,
                barcode=barcode,
                size=size,
                **validated_data
            )

            ProductBatch.objects.create(
                product=product,
                quantity=quantity,
                purchase_price=purchase_price,
                supplier=supplier,
                expiration_date=expiration_date
            )

            product.generate_label()
            created_products.append(product)

        return created_products

    def _generate_unique_barcode(self):
        import random
        import time

        while True:
            timestamp = str(int(time.time()))[-8:]
            random_part = str(random.randint(1000, 9999))
            barcode = timestamp + random_part
            if not Product.objects.filter(barcode=barcode).exists():
                return barcode

# class ProductMultiSizeCreateSerializer(serializers.Serializer):
#     """
#     Сериализатор для создания товаров с множественными размерами
#     """
#     name = serializers.CharField(max_length=255)
#     category = serializers.PrimaryKeyRelatedField(queryset=ProductCategory.objects.all())
#     sale_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
#     unit = serializers.ChoiceField(choices=Product.UNIT_CHOICES, default='piece')

#     # Список ID размеров, которые нужно создать
#     size_ids = serializers.ListField(
#         child=serializers.PrimaryKeyRelatedField(queryset=SizeInfo.objects.all()),
#         allow_empty=False,
#         help_text="Список ID размеров для создания отдельных товаров"
#     )

#     # Информация о партии (опционально)
#     batch_info = serializers.DictField(required=False, help_text="Информация о партии")

#     def validate_name(self, value):
#         return value.strip()

#     def validate_sale_price(self, value):
#         return round(value, 2)

#     def create(self, validated_data):
#         """
#         Создает отдельный Product для каждого выбранного размера
#         """
#         size_ids = validated_data.pop('size_ids')
#         batch_info = validated_data.pop('batch_info', None)
#         base_name = validated_data['name']

#         created_products = []

#         for size in size_ids:
#             # Создаем уникальное название с размером
#             product_name = f"{base_name} - {size.size}"

#             # Генерируем уникальный штрих-код
#             barcode = self._generate_unique_barcode()

#             # Создаем товар
#             product_data = {
#                 **validated_data,
#                 'name': product_name,
#                 'barcode': barcode,
#                 'size': size
#             }

#             product = Product.objects.create(**product_data)

#             # Создаем партию если указана
#             if batch_info:
#                 ProductBatch.objects.create(
#                     product=product,
#                     **batch_info
#                 )

#             # Генерируем этикетку
#             product.generate_label()

#             created_products.append(product)

#         return created_products

#     def _generate_unique_barcode(self):
#         """
#         Генерирует уникальный штрих-код
#         """
#         import random
#         import time

#         while True:
#             # Генерируем штрих-код из текущего времени и случайного числа
#             timestamp = str(int(time.time()))[-8:]  # Последние 8 цифр времени
#             random_part = str(random.randint(1000, 9999))  # 4 случайные цифры
#             barcode = timestamp + random_part

#             # Проверяем уникальность
#             if not Product.objects.filter(barcode=barcode).exists():
#                 return barcode
############################################################### Продукты конец #############################################################

