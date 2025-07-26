# inventory/serializers.py
from rest_framework import serializers
from .models import Product, ProductCategory, Stock, ProductBatch, UnitOfMeasure, MeasurementCategory
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from drf_yasg.utils import swagger_serializer_method





class MeasurementCategorySerializer(serializers.ModelSerializer):
    """Сериализатор для категорий единиц измерения"""
    units_count = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = MeasurementCategory
        fields = ['id', 'name', 'allow_fraction', 'base_unit_name', 'units_count']
        
    def get_units_count(self, obj):
        """Количество единиц в категории"""
        return obj.units.count()


class MeasurementCategoryDetailSerializer(serializers.ModelSerializer):
    """Детальный сериализатор для категорий с единицами измерения"""
    units = serializers.SerializerMethodField()
    units_count = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = MeasurementCategory
        fields = ['id', 'name', 'allow_fraction', 'base_unit_name', 'units_count', 'units']
        
    def get_units_count(self, obj):
        """Количество единиц в категории"""
        return obj.units.count()
        
    def get_units(self, obj):
        """Список единиц измерения в категории"""
        units = obj.units.filter(is_active=True).order_by('name')
        return UnitOfMeasureSerializer(units, many=True).data


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    """Сериализатор для единиц измерения"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = UnitOfMeasure
        fields = [
            'id', 'name', 'short_name', 'category', 'category_name',
            'conversion_factor', 'is_active', 'created_at'
        ]
        read_only_fields = ['created_at']
        
    def validate_conversion_factor(self, value):
        """Валидация коэффициента конвертации"""
        if value <= 0:
            raise serializers.ValidationError("Коэффициент конвертации должен быть больше 0")
        return value
        
    def validate(self, data):
        """Дополнительная валидация"""
        # Проверяем, что short_name уникально в рамках категории
        category = data.get('category')
        short_name = data.get('short_name')
        
        if category and short_name:
            existing = UnitOfMeasure.objects.filter(
                category=category, 
                short_name=short_name
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise serializers.ValidationError({
                    'short_name': 'Единица с таким коротким названием уже существует в данной категории'
                })
        
        return data


class UnitOfMeasureDetailSerializer(serializers.ModelSerializer):
    """Детальный сериализатор для единиц измерения"""
    category = MeasurementCategorySerializer(read_only=True)
    products_count = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = UnitOfMeasure
        fields = [
            'id', 'name', 'short_name', 'category',
            'conversion_factor', 'is_active', 'created_at', 'products_count'
        ]
        read_only_fields = ['created_at']
        
    def get_products_count(self, obj):
        """Количество товаров использующих эту единицу"""
        return obj.products.count()


class UnitConversionSerializer(serializers.Serializer):
    """Сериализатор для конвертации между единицами измерения"""
    value = serializers.DecimalField(max_digits=10, decimal_places=6)
    from_unit_id = serializers.IntegerField()
    to_unit_id = serializers.IntegerField()
    
    def validate(self, data):
        """Валидация данных для конвертации"""
        try:
            from_unit = UnitOfMeasure.objects.get(id=data['from_unit_id'])
            to_unit = UnitOfMeasure.objects.get(id=data['to_unit_id'])
        except UnitOfMeasure.DoesNotExist:
            raise serializers.ValidationError("Одна из указанных единиц измерения не найдена")
            
        if from_unit.category != to_unit.category:
            raise serializers.ValidationError("Единицы измерения должны быть из одной категории")
            
        data['from_unit'] = from_unit
        data['to_unit'] = to_unit
        return data


class UnitConversionResultSerializer(serializers.Serializer):
    """Сериализатор для результата конвертации"""
    original_value = serializers.DecimalField(max_digits=10, decimal_places=6)
    converted_value = serializers.DecimalField(max_digits=10, decimal_places=6)
    from_unit = UnitOfMeasureSerializer()
    to_unit = UnitOfMeasureSerializer()
    conversion_formula = serializers.CharField()

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


class ProductSerializer(serializers.ModelSerializer):

    unit_detail = serializers.SerializerMethodField(read_only=True)

    category = serializers.PrimaryKeyRelatedField(
        queryset=ProductCategory.objects.all(),
        error_messages={
            'does_not_exist': _('Указанная категория не существует'),
            'incorrect_type': _('Некорректный тип данных для категории')
        }
    )
    
    current_stock = serializers.IntegerField(
        source='stock.quantity',
        read_only=True,
        help_text=_('Текущий остаток на складе')
    )
    unit = serializers.PrimaryKeyRelatedField(
        queryset=UnitOfMeasure.objects.filter(is_active=True),
        write_only=True,
        help_text="ID единицы измерения"
    )

    @swagger_serializer_method(serializer_or_field=serializers.IntegerField)
    def get_current_stock(self, obj):
        return obj.stock.quantity if hasattr(obj, 'stock') else 0
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'barcode', 'category',
            'unit', 'unit_detail', 'sale_price', 'created_at', 'current_stock'
        ]
        read_only_fields = ['created_at', 'current_stock']
        extra_kwargs = {
            'name': {'trim_whitespace': True},
            'barcode': {
                'required': False,
                'allow_null': True,
                'allow_blank': True
            }
        }
        swagger_schema_fields = {
            'example': {
                'name': 'Кока-Кола 0.5л',
                'barcode': '5449000000996',
                'category': 1,
                'unit': 2,  # ID единицы измерения, например 2
                'sale_price': 89.90
            }
        }

    def get_unit_detail(self, obj):
        if obj.unit:
            return UnitOfMeasureSerializer(obj.unit).data
        return None

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

class ProductBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_unit = serializers.CharField(source='product.get_unit_display', read_only=True)

    class Meta:
        model = ProductBatch
        fields = ['id', 'product', 'product_name', 'product_unit', 'quantity', 'expiration_date', 'created_at', 'purchase_price', 'supplier']
        read_only_fields = ['created_at', 'product_name', 'product_unit']
        extra_kwargs = {
            'expiration_date': {'required': False, 'allow_null': True},
            'purchase_price': {'required': False, 'allow_null': True},
            'supplier': {'trim_whitespace': True, 'required': False, 'allow_blank': True},
            'quantity': {'default': 1}
        }
        ref_name = 'ProductBatchSerializerInventory'

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
    
# class ProductBatchSerializer(serializers.ModelSerializer):
#     product_name = serializers.CharField(
#         source='product.name',
#         read_only=True
#     )
    
#     product_unit = serializers.CharField(
#         source='product.get_unit_display',
#         read_only=True
#     )

#     class Meta:
#         model = ProductBatch
#         fields = [
#             'id', 'product', 'product_name', 'product_unit',
#             'quantity', 'expiration_date', 'created_at',
#             'purchase_price', 'supplier'
#         ]
#         read_only_fields = ['created_at']
#         extra_kwargs = {
#             'expiration_date': {'required': False, 'allow_null': True},
#             'purchase_price': {'required': False, 'allow_null': True},
#             'supplier': {'trim_whitespace': True}
#         }
#         swagger_schema_fields = {
#             'example': {
#                 'product': 1,
#                 'quantity': 100,
#                 'expiration_date': '2024-12-31',
#                 'purchase_price': 50.00,
#                 'supplier': 'ООО Напитки'
#             }
#         }


#     def validate_quantity(self, value):
#         if value <= 0:
#             raise serializers.ValidationError(
#                 _("Количество должно быть больше нуля"),
#                 code='invalid_quantity'
#             )
#         return value

#     def validate(self, data):
#         """
#         Проверка, что срок годности не в прошлом
#         """
#         expiration_date = data.get('expiration_date')
#         if expiration_date and expiration_date < timezone.now().date():
#             raise serializers.ValidationError(
#                 {'expiration_date': _("Срок годности не может быть в прошлом")},
#                 code='expired_product'
#             )
#         return data


class SaleSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(
        min_value=1,
        help_text=_('ID товара для продажи')
    )
    
    quantity = serializers.IntegerField(
        min_value=1,
        help_text=_('Количество товара для продажи')
    )

    def validate_product_id(self, value):
        if not Product.objects.filter(id=value).exists():
            raise serializers.ValidationError(
                _("Товар с ID %(product_id)s не найден"),
                params={'product_id': value},
                code='product_not_found'
            )
        return value

    def validate(self, data):
        product = Product.objects.get(id=data['product_id'])
        if product.stock.quantity < data['quantity']:
            raise serializers.ValidationError(
                {
                    'quantity': _(
                        "Недостаточно товара на складе. Доступно: %(available)s"
                    ) % {'available': product.stock.quantity}
                },
                code='insufficient_stock'
            )
        return data
    
    class Meta:
        swagger_schema_fields = {
            'example': {
                'product_id': 1,
                'quantity': 2
            }
        }