# inventory/serializers.py
from rest_framework import serializers
from .models import Product, ProductCategory, Stock, ProductBatch

class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['created_at']
    def validate_name(self, value):
        if ProductCategory.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("Категория с таким названием уже существует")
        return value

class ProductSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=ProductCategory.objects.all())
    barcode = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    class Meta:
        model = Product
        fields = ['id', 'name', 'barcode', 'category', 'unit', 'sale_price', 'created_at']
        read_only_fields = ['created_at']
    def validate_sale_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Цена не может быть отрицательной")
        return value
    def validate_barcode(self, value):
        if value and Product.objects.filter(barcode=value).exclude(pk=self.instance.pk if self.instance else None).exists():
            raise serializers.ValidationError("Штрихкод уже существует")
        if value and not (value.isdigit() and 1 <= len(value) <= 100):
            raise serializers.ValidationError("Штрихкод должен быть числом до 100 цифр")
        return value

class StockSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    class Meta:
        model = Stock
        fields = ['product', 'quantity', 'updated_at']
        read_only_fields = ['updated_at']
    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Количество не может быть отрицательным")
        return value

class ProductBatchSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    class Meta:
        model = ProductBatch
        fields = ['id', 'product', 'quantity', 'expiration_date', 'created_at']
        read_only_fields = ['created_at']
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Количество должно быть больше 0")
        return value

class SaleSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    def validate_product_id(self, value):
        if not Product.objects.filter(id=value).exists():
            raise serializers.ValidationError("Продукт не найден")
        return value