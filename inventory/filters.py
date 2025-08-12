# inventory/filters.py
import django_filters
from django.db.models import Q
from .models import Product, ProductBatch, Stock, AttributeType, AttributeValue


class ProductFilter(django_filters.FilterSet):
    """
    Расширенные фильтры для товаров
    """
    name = django_filters.CharFilter(lookup_expr='icontains', label='Название содержит')
    barcode = django_filters.CharFilter(lookup_expr='exact', label='Точный штрих-код')
    category = django_filters.NumberFilter(field_name='category', label='Категория')

    # --- фильтры по создателю ---
    created_by = django_filters.NumberFilter(
        field_name='created_by__id',
        lookup_expr='exact',
        label='ID создателя'
    )
    created_by_username = django_filters.CharFilter(
        field_name='created_by__username',
        lookup_expr='iexact',
        label='Имя создателя'
    )

    # --- фильтрация по атрибутам ---
    brand = django_filters.ModelChoiceFilter(
        queryset=AttributeValue.objects.filter(attribute_type__slug='brand'),
        field_name='attributes',
        label='Бренд'
    )

    size = django_filters.ModelChoiceFilter(
        queryset=AttributeValue.objects.filter(attribute_type__slug='size'),
        field_name='attributes',
        label='Размер'
    )

    color = django_filters.ModelChoiceFilter(
        queryset=AttributeValue.objects.filter(attribute_type__slug='color'),
        field_name='attributes',
        label='Цвет'
    )

    # --- фильтрация по остаткам ---
    min_stock = django_filters.NumberFilter(
        field_name='stock__quantity',
        lookup_expr='gte',
        label='Минимальный остаток'
    )

    max_stock = django_filters.NumberFilter(
        field_name='stock__quantity',
        lookup_expr='lte',
        label='Максимальный остаток'
    )

    # --- фильтрация по цене ---
    min_price = django_filters.NumberFilter(
        field_name='sale_price',
        lookup_expr='gte',
        label='Минимальная цена'
    )

    max_price = django_filters.NumberFilter(
        field_name='sale_price',
        lookup_expr='lte',
        label='Максимальная цена'
    )

    # --- специальные фильтры ---
    has_stock = django_filters.BooleanFilter(
        method='filter_has_stock',
        label='Есть на складе'
    )

    low_stock = django_filters.BooleanFilter(
        method='filter_low_stock',
        label='Низкий остаток'
    )

    class Meta:
        model = Product
        fields = [
            'name', 'barcode', 'category', 'brand', 'size', 'color',
            'min_stock', 'max_stock', 'min_price', 'max_price',
            'has_stock', 'low_stock', 'created_by', 'created_by_username'
        ]

    def filter_has_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock__quantity__gt=0)
        return queryset.filter(stock__quantity=0)

    def filter_low_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock__quantity__lte=10, stock__quantity__gt=0)
        return queryset


class ProductBatchFilter(django_filters.FilterSet):
    """
    Фильтры для партий товаров
    """
    product_name = django_filters.CharFilter(
        field_name='product__name',
        lookup_expr='icontains',
        label='Название товара'
    )

    supplier = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Поставщик'
    )

    min_quantity = django_filters.NumberFilter(
        field_name='quantity',
        lookup_expr='gte',
        label='Минимальное количество'
    )

    max_quantity = django_filters.NumberFilter(
        field_name='quantity',
        lookup_expr='lte',
        label='Максимальное количество'
    )

    created_from = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='gte',
        label='Создано с'
    )

    created_to = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='lte',
        label='Создано до'
    )

    expires_from = django_filters.DateFilter(
        field_name='expiration_date',
        lookup_expr='gte',
        label='Истекает с'
    )

    expires_to = django_filters.DateFilter(
        field_name='expiration_date',
        lookup_expr='lte',
        label='Истекает до'
    )

    expiring_soon = django_filters.BooleanFilter(
        method='filter_expiring_soon',
        label='Истекает скоро'
    )

    class Meta:
        model = ProductBatch
        fields = [
            'product', 'product_name', 'supplier', 'min_quantity', 'max_quantity',
            'created_from', 'created_to', 'expires_from', 'expires_to', 'expiring_soon'
        ]

    def filter_expiring_soon(self, queryset, name, value):
        if value:
            from datetime import date, timedelta
            expiry_date = date.today() + timedelta(days=7)
            return queryset.filter(
                expiration_date__lte=expiry_date,
                expiration_date__isnull=False
            )
        return queryset


class StockFilter(django_filters.FilterSet):
    """
    Фильтры для остатков на складе
    """
    product_name = django_filters.CharFilter(
        field_name='product__name',
        lookup_expr='icontains',
        label='Название товара'
    )

    product_barcode = django_filters.CharFilter(
        field_name='product__barcode',
        lookup_expr='exact',
        label='Штрих-код товара'
    )

    category = django_filters.NumberFilter(
        field_name='product__category',
        label='Категория'
    )

    min_quantity = django_filters.NumberFilter(
        field_name='quantity',
        lookup_expr='gte',
        label='Минимальное количество'
    )

    max_quantity = django_filters.NumberFilter(
        field_name='quantity',
        lookup_expr='lte',
        label='Максимальное количество'
    )

    zero_stock = django_filters.BooleanFilter(
        method='filter_zero_stock',
        label='Нулевой остаток'
    )

    low_stock = django_filters.BooleanFilter(
        method='filter_low_stock',
        label='Низкий остаток'
    )

    class Meta:
        model = Stock
        fields = [
            'product', 'product_name', 'product_barcode', 'category',
            'min_quantity', 'max_quantity', 'zero_stock', 'low_stock'
        ]

    def filter_zero_stock(self, queryset, name, value):
        if value:
            return queryset.filter(quantity=0)
        return queryset.filter(quantity__gt=0)

    def filter_low_stock(self, queryset, name, value):
        if value:
            return queryset.filter(quantity__lte=10, quantity__gt=0)
        return queryset