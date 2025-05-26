from rest_framework import serializers
from .models import Product, ProductCategory, Stock, ProductBatch

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'barcode', 'category', 'unit', 'sale_price', 'created_at']


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

    class Meta:
        model = Product
        fields = ['id', 'name', 'barcode', 'category', 'unit', 'sale_price', 'created_at']
        read_only_fields = ['barcode', 'created_at']

    def validate_sale_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Цена не может быть отрицательной")
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