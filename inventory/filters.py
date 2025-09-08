# inventory/filters.py
import django_filters
from django_filters import rest_framework as filters
from django.db.models import Q
from .models import Product, ProductBatch, Stock, AttributeType, AttributeValue, SizeInfo


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

class SizeInfoFilter(filters.FilterSet):
    """
    Фильтр для размерной информации
    """
    # Фильтр по размеру (точное совпадение и множественный выбор)
    size = filters.MultipleChoiceFilter(
        choices=SizeInfo.SIZE_CHOICES,
        field_name='size',
        lookup_expr='exact'
    )

    # Фильтр по обхвату груди (диапазон)
    chest_min = filters.NumberFilter(
        field_name='chest',
        lookup_expr='gte',
        label='Минимальный обхват груди'
    )
    chest_max = filters.NumberFilter(
        field_name='chest',
        lookup_expr='lte',
        label='Максимальный обхват груди'
    )
    chest = filters.RangeFilter(
        field_name='chest',
        label='Диапазон обхвата груди'
    )

    # Фильтр по обхвату талии (диапазон)
    waist_min = filters.NumberFilter(
        field_name='waist',
        lookup_expr='gte',
        label='Минимальный обхват талии'
    )
    waist_max = filters.NumberFilter(
        field_name='waist',
        lookup_expr='lte',
        label='Максимальный обхват талии'
    )
    waist = filters.RangeFilter(
        field_name='waist',
        label='Диапазон обхвата талии'
    )

    # Фильтр по длине (диапазон)
    length_min = filters.NumberFilter(
        field_name='length',
        lookup_expr='gte',
        label='Минимальная длина'
    )
    length_max = filters.NumberFilter(
        field_name='length',
        lookup_expr='lte',
        label='Максимальная длина'
    )
    length = filters.RangeFilter(
        field_name='length',
        label='Диапазон длины'
    )

    # Фильтр для поиска по всем размерам (содержит)
    size_contains = filters.CharFilter(
        field_name='size',
        lookup_expr='icontains',
        label='Поиск по размеру (содержит)'
    )

    # Фильтр для пустых значений
    has_chest = filters.BooleanFilter(
        field_name='chest',
        lookup_expr='isnull',
        exclude=True,
        label='Есть данные об обхвате груди'
    )
    has_waist = filters.BooleanFilter(
        field_name='waist',
        lookup_expr='isnull',
        exclude=True,
        label='Есть данные об обхвате талии'
    )
    has_length = filters.BooleanFilter(
        field_name='length',
        lookup_expr='isnull',
        exclude=True,
        label='Есть данные о длине'
    )

    class Meta:
        model = SizeInfo
        fields = {
            'size': ['exact', 'in'],
            'chest': ['exact', 'gte', 'lte', 'range'],
            'waist': ['exact', 'gte', 'lte', 'range'],
            'length': ['exact', 'gte', 'lte', 'range'],
        }

    def filter_by_measurements(self, queryset, name, value):
        """
        Кастомный фильтр для поиска по приближенным размерам
        """
        if value:
            # Логика для поиска подходящих размеров по параметрам
            return queryset.filter(
                chest__lte=value + 5,
                chest__gte=value - 5
            )
        return queryset


# inventory/filters.py - обновленный ProductFilter
import django_filters
from django_filters import rest_framework as filters
from django.db.models import Q
from .models import Product, ProductBatch, Stock, AttributeType, AttributeValue, SizeInfo

class ProductFilter(django_filters.FilterSet):
    """
    Расширенные фильтры для товаров с поддержкой SizeInfo
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

    # ========== НОВАЯ ФИЛЬТРАЦИЯ ПО РАЗМЕРАМ ЧЕРЕЗ SizeInfo ==========

    # Фильтр по размеру (точное совпадение)
    size = django_filters.CharFilter(
        field_name='size__size',
        lookup_expr='exact',
        label='Размер (точное совпадение)'
    )

    # Фильтр по размеру (множественный выбор)
    sizes = django_filters.MultipleChoiceFilter(
        field_name='size__size',
        choices=SizeInfo.SIZE_CHOICES,
        label='Размеры (множественный выбор)'
    )

    # Фильтр по размеру (содержит)
    size_contains = django_filters.CharFilter(
        field_name='size__size',
        lookup_expr='icontains',
        label='Размер (содержит)'
    )

    # Фильтр по ID размера
    size_id = django_filters.NumberFilter(
        field_name='size__id',
        lookup_expr='exact',
        label='ID размера'
    )

    # Фильтры по параметрам размера
    chest_min = django_filters.NumberFilter(
        field_name='size__chest',
        lookup_expr='gte',
        label='Минимальный обхват груди'
    )
    chest_max = django_filters.NumberFilter(
        field_name='size__chest',
        lookup_expr='lte',
        label='Максимальный обхват груди'
    )

    waist_min = django_filters.NumberFilter(
        field_name='size__waist',
        lookup_expr='gte',
        label='Минимальный обхват талии'
    )
    waist_max = django_filters.NumberFilter(
        field_name='size__waist',
        lookup_expr='lte',
        label='Максимальный обхват талии'
    )

    length_min = django_filters.NumberFilter(
        field_name='size__length',
        lookup_expr='gte',
        label='Минимальная длина'
    )
    length_max = django_filters.NumberFilter(
        field_name='size__length',
        lookup_expr='lte',
        label='Максимальная длина'
    )

    # Кастомный фильтр для поиска подходящего размера по параметрам
    suitable_size = django_filters.CharFilter(
        method='filter_suitable_size',
        label='Подходящий размер (chest,waist,length)'
    )

    # Фильтр для товаров с размером или без
    has_size = django_filters.BooleanFilter(
        field_name='size',
        lookup_expr='isnull',
        exclude=True,
        label='Есть размерная информация'
    )

    # ========== СТАРЫЕ ФИЛЬТРЫ ПО АТРИБУТАМ (можно оставить для совместимости) ==========

    brand = django_filters.ModelChoiceFilter(
        queryset=AttributeValue.objects.filter(attribute_type__slug='brand'),
        field_name='attributes',
        label='Бренд'
    )

    # Старый фильтр по размеру через атрибуты (для совместимости)
    size_attribute = django_filters.ModelChoiceFilter(
        queryset=AttributeValue.objects.filter(attribute_type__slug='size'),
        field_name='attributes',
        label='Размер (через атрибуты)'
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
            'name', 'barcode', 'category',
            # Новые поля для размеров
            'size', 'sizes', 'size_contains', 'size_id',
            'chest_min', 'chest_max', 'waist_min', 'waist_max',
            'length_min', 'length_max', 'has_size', 'suitable_size',
            # Старые поля
            'brand', 'size_attribute', 'color',
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

    def filter_suitable_size(self, queryset, name, value):
        """
        Кастомный фильтр для поиска подходящих размеров по параметрам
        Формат: "chest,waist,length" например "90,75,60"
        """
        if not value:
            return queryset

        try:
            params = value.split(',')
            if len(params) != 3:
                return queryset

            chest = int(params[0]) if params[0] else None
            waist = int(params[1]) if params[1] else None
            length = int(params[2]) if params[2] else None

            # Создаем Q-объекты для фильтрации с допуском ±5
            q_filter = Q()

            if chest:
                q_filter &= Q(size__chest__gte=chest-5, size__chest__lte=chest+5)
            if waist:
                q_filter &= Q(size__waist__gte=waist-5, size__waist__lte=waist+5)
            if length:
                q_filter &= Q(size__length__gte=length-5, size__length__lte=length+5)

            return queryset.filter(q_filter)

        except (ValueError, TypeError):
            return queryset


# ========== РАСШИРЕННЫЙ ФИЛЬТР С КОМБИНИРОВАННОЙ ЛОГИКОЙ ==========

class AdvancedProductFilter(ProductFilter):
    """
    Расширенный фильтр с дополнительными возможностями
    """

    # Комбинированный поиск по размерам (и в SizeInfo, и в атрибутах)
    any_size = django_filters.CharFilter(
        method='filter_any_size',
        label='Размер (поиск везде)'
    )

    # Фильтр по размерному диапазону
    size_range = django_filters.CharFilter(
        method='filter_size_range',
        label='Диапазон размеров (например: S-L)'
    )

    def filter_any_size(self, queryset, name, value):
        """
        Ищет размер и в SizeInfo, и в атрибутах
        """
        if not value:
            return queryset

        return queryset.filter(
            Q(size__size__icontains=value) |  # В SizeInfo
            Q(attributes__value__icontains=value, attributes__attribute_type__slug='size')  # В атрибутах
        ).distinct()

    def filter_size_range(self, queryset, name, value):
        """
        Фильтрует по диапазону размеров (например: S-L вернет S, M, L)
        """
        if not value or '-' not in value:
            return queryset

        try:
            start_size, end_size = value.split('-')
            size_order = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']

            start_idx = size_order.index(start_size.strip().upper())
            end_idx = size_order.index(end_size.strip().upper())

            if start_idx > end_idx:
                start_idx, end_idx = end_idx, start_idx

            sizes_in_range = size_order[start_idx:end_idx+1]

            return queryset.filter(size__size__in=sizes_in_range)

        except (ValueError, IndexError):
            return queryset