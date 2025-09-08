
# inventory/views.py
from rest_framework import status, generics, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from django.db import transaction, models
from django.db.models import Q, Sum, Prefetch
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, NumberFilter, CharFilter
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.pagination import LimitOffsetPagination
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import logging
from django.core.exceptions import ValidationError
from rest_framework import pagination
from .pagination import OptionalPagination
from stores.mixins import StoreViewSetMixin, StoreSerializerMixin, StorePermissionMixin

from customers.views import FlexiblePagination

from .models import (
    Product, ProductCategory, Stock, ProductBatch,
    AttributeType, AttributeValue, ProductAttribute,
    SizeChart, SizeInfo
)
from .serializers import (
    ProductSerializer, ProductCategorySerializer, StockSerializer,
    ProductBatchSerializer, AttributeTypeSerializer, AttributeValueSerializer,
    ProductAttributeSerializer, SizeChartSerializer, SizeInfoSerializer,
    ProductMultiSizeCreateSerializer
)

from .filters import ProductFilter, ProductBatchFilter, StockFilter, SizeInfoFilter
# в одном из ваших приложений views.py
from django.http import HttpResponse, Http404
from django.conf import settings
import os

def serve_media(request, path):
    try:
        media_path = os.path.join(settings.MEDIA_ROOT, path)
        with open(media_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='image/png')
            response['Access-Control-Allow-Origin'] = 'http://localhost:5173'
            return response
    except:
        raise Http404




logger = logging.getLogger('inventory')

class SizeInfoPagination(LimitOffsetPagination):
    """
    Кастомная пагинация для SizeInfo
    """
    default_limit = 20
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.count,
            'limit': self.limit,
            'offset': self.offset,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })

class CustomPagination(LimitOffsetPagination):
    """
    Кастомная пагинация с настраиваемыми параметрами
    """
    default_limit = 20
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.count,
            'limit': self.limit,
            'offset': self.offset,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })

class ProductCategoryViewSet(StoreViewSetMixin, ModelViewSet):
    """
    ViewSet для управления категориями товаров
    """
    pagination_class = CustomPagination
    serializer_class = ProductCategorySerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        current_store = getattr(self.request.user, 'current_store', None)
        if current_store:
            return ProductCategory.objects.filter(store=current_store)
        return ProductCategory.objects.none()



class AttributeTypeViewSet(ModelViewSet):
    """
    ViewSet для управления типами атрибутов (динамические атрибуты)
    """
    queryset = AttributeType.objects.prefetch_related('values').all()
    serializer_class = AttributeTypeSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'slug']
    ordering_fields = ['name']
    ordering = ['name']

    @swagger_auto_schema(
        operation_description="Получить все типы атрибутов с их значениями",
        responses={200: AttributeTypeSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def for_product_creation(self, request):
        """
        Получить все активные атрибуты для создания товара
        """
        attributes = self.get_queryset().filter(values__isnull=False).distinct()
        serializer = self.get_serializer(attributes, many=True)
        return Response({
            'attributes': serializer.data,
            'message': _('Доступные атрибуты для создания товара')
        })


class AttributeValueViewSet(ModelViewSet):
    """
    ViewSet для управления значениями атрибутов
    """
    queryset = AttributeValue.objects.select_related('attribute_type').all()
    serializer_class = AttributeValueSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['attribute_type']
    search_fields = ['value']




class ProductViewSet(
    StoreViewSetMixin,
    StorePermissionMixin,   # ✅ этот можно оставить
    viewsets.ModelViewSet
):
    pagination_class = FlexiblePagination
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'barcode', 'category__name', 'created_by__username']
    filterset_fields = ['category', 'created_by']
    ordering_fields = ['name', 'sale_price', 'created_at']
    ordering = ['-created_at']

    queryset = Product.objects.select_related("category", "stock").prefetch_related("size", "batches")
    # def get_queryset(self):
    #     # ✅ получаем текущий магазин
    #     current_store = self.get_current_store()

    #     # если магазин не найден — возвращаем пустой queryset
    #     if not current_store:
    #         return Product.objects.none()

    #     return Product.objects.filter(
    #         store=current_store  # 🔥 фильтрация по магазину
    #     ).select_related(
    #         'category', 'stock'
    #     ).prefetch_related(
    #         'size',
    #         'batches'
    #     )


    @swagger_auto_schema(
        operation_description="Создать товары для множественных размеров",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'name': openapi.Schema(type=openapi.TYPE_STRING, description='Базовое название товара'),
                'category': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID категории'),
                'sale_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Цена продажи'),
                'unit': openapi.Schema(type=openapi.TYPE_STRING, description='Единица измерения'),
                'size_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                    description='Массив ID размеров'
                ),
                'batch_info': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'purchase_price': openapi.Schema(type=openapi.TYPE_NUMBER),
                        'supplier': openapi.Schema(type=openapi.TYPE_STRING),
                        'expiration_date': openapi.Schema(type=openapi.TYPE_STRING, format='date', nullable=True)
                    },
                    required=[]
                )
            },
            required=['name', 'category', 'sale_price', 'size_ids']
        ),
        responses={
            201: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'products': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT)
                    ),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER)
                }
            ),
            400: 'Ошибка валидации'
        }
    )

# {
#     "name": "Футболка Армани",
#     "category": 1,
#     "sale_price": 150000.00,
#     "unit": "piece",
#     "size_ids": [1, 2, 3, 4],  // ID размеров S, M, L, XL
#     "batch_info": {
#         "quantity": 10,
#         "purchase_price": 100000.00,
#         "supplier": "Армани Official",
#         "expiration_date": null
#     }
# }


    @action(detail=False, methods=['post'])
    def create_multi_size(self, request):
        """
        Создание товаров с множественными размерами.
        Каждый размер создается как отдельный Product с уникальным штрих-кодом.
        """
        # Проверяем аутентификацию
        if not request.user.is_authenticated:
            return Response({
                'error': _('Необходима аутентификация')
            }, status=status.HTTP_401_UNAUTHORIZED)

        # ✅ ВАЖНО: Получаем текущий магазин
        current_store = self.get_current_store()
        if not current_store:
            return Response({
                'error': 'Магазин не определен. Переавторизуйтесь или выберите магазин.',
                'debug_info': {
                    'user': request.user.username,
                    'has_current_store': hasattr(request.user, 'current_store'),
                    'current_store_value': getattr(request.user, 'current_store', None)
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = ProductMultiSizeCreateSerializer(data=request.data)

        if serializer.is_valid():
            try:
                with transaction.atomic():
                    # ✅ Передаем created_by И store
                    created_products = serializer.save(
                        created_by=request.user,
                        store=current_store  # ← ДОБАВЛЕНО
                    )

                # Сериализуем созданные товары для ответа
                products_data = ProductSerializer(created_products, many=True, context={'request': request}).data

                logger.info(f"Создано {len(created_products)} товаров с размерами пользователем {request.user.username}")

                return Response({
                    'products': products_data,
                    'message': _('Товары успешно созданы для всех размеров'),
                    'count': len(created_products),
                    'action': 'multi_size_products_created'
                }, status=status.HTTP_201_CREATED)

            except Exception as e:
                logger.error(f"Ошибка при создании товаров с размерами: {str(e)}")
                return Response({
                    'error': _('Ошибка при создании товаров'),
                    'details': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Также добавь этот вспомогательный endpoint для получения размеров
    @action(detail=False, methods=['get'])
    def available_sizes(self, request):
        """
        Получить все доступные размеры для создания товаров
        """
        sizes = SizeInfo.objects.all().order_by('size')
        serializer = SizeInfoSerializer(sizes, many=True)

        return Response({
            'sizes': serializer.data,
            'count': sizes.count(),
            'message': _('Доступные размеры для товаров')
        })

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """✅ ИСПРАВЛЕННОЕ создание товара с правильной последовательностью"""
        barcode = request.data.get('barcode')
        batch_info = request.data.pop('batch_info', {})
        size_id = request.data.pop('size_id', None)

        # Получаем текущий магазин
        current_store = self.get_current_store() if hasattr(self, 'get_current_store') else getattr(request.user, 'current_store', None)

        if not current_store:
            return Response({
                'error': 'Магазин не определен. Переавторизуйтесь.',
                'debug_info': {
                    'user': request.user.username,
                    'has_current_store': hasattr(request.user, 'current_store')
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        # Проверяем существование товара по штрих-коду В ТЕКУЩЕМ МАГАЗИНЕ
        if barcode:
            existing_product = Product.objects.filter(
                store=current_store,
                barcode=barcode
            ).first()

            if existing_product:
                # Товар существует - добавляем партию
                if batch_info:
                    batch_data = {
                        'product': existing_product.id,
                        **batch_info
                    }
                    batch_serializer = ProductBatchSerializer(
                        data=batch_data,
                        context={'request': request}
                    )
                    if batch_serializer.is_valid():
                        # perform_create в StoreViewSetMixin автоматически добавит store
                        self.perform_create(batch_serializer)
                        logger.info(f"✅ Batch added to existing product {existing_product.name}")
                    else:
                        return Response(
                            {'batch_errors': batch_serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                serializer = self.get_serializer(existing_product)
                return Response({
                    'product': serializer.data,
                    'message': _('Партия добавлена к существующему товару'),
                    'action': 'batch_added'
                }, status=status.HTTP_200_OK)

        # ✅ СОЗДАЕМ НОВЫЙ ТОВАР - ПРАВИЛЬНАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ

        # 1. Валидируем данные
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # 2. Создаем товар через perform_create (установит store автоматически)
        self.perform_create(serializer)
        product = serializer.instance

        # 3. Теперь у product есть store, можем создать Stock вручную если нужно
        if not hasattr(product, 'stock'):
            try:
                Stock.objects.create(
                    product=product,
                    store=product.store,  # ← Теперь у product точно есть store
                    quantity=0
                )
                logger.info(f"✅ Stock manually created for {product.name}")
            except Exception as e:
                logger.error(f"❌ Error creating stock: {str(e)}")

        # 4. Обрабатываем размер
        if size_id:
            try:
                size_instance = SizeInfo.objects.get(id=size_id)
                product.size = size_instance
                product.save()
                logger.info(f"✅ Size {size_instance.size} set for {product.name}")
            except SizeInfo.DoesNotExist:
                return Response(
                    {'size_error': _('Размерная информация не найдена')},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 5. Создаем партию если указана
        if batch_info:
            batch_data = {
                'product': product.id,
                **batch_info
            }
            batch_serializer = ProductBatchSerializer(
                data=batch_data,
                context={'request': request}
            )
            if batch_serializer.is_valid():
                # perform_create добавит store к batch автоматически
                batch_viewset = ProductBatchViewSet()
                batch_viewset.request = request
                batch_viewset.perform_create(batch_serializer)
                logger.info(f"✅ Batch created for new product {product.name}")
            else:
                return Response(
                    {'batch_errors': batch_serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 6. Генерируем этикетку
        try:
            product.generate_label()
            logger.info(f"✅ Label generated for {product.name}")
        except Exception as e:
            logger.error(f"⚠️ Label generation failed: {str(e)}")

        # 7. Возвращаем результат
        updated_serializer = self.get_serializer(product)
        return Response({
            'product': updated_serializer.data,
            'message': _('Товар успешно создан'),
            'action': 'product_created'
        }, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        Обновление товара с атрибутами
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            product = serializer.save()

            # Обновляем атрибуты если переданы
            if 'attributes' in request.data:
                self._handle_product_attributes(product, request.data['attributes'])

            updated_serializer = self.get_serializer(product)
            return Response(updated_serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _handle_product_attributes(self, product, attributes_data):
        """
        Обработка атрибутов товара
        """
        if not attributes_data:
            return

        # Удаляем старые атрибуты
        ProductAttribute.objects.filter(product=product).delete()

        # Добавляем новые атрибуты
        for attr_data in attributes_data:
            attribute_value_id = attr_data.get('attribute_id')
            if attribute_value_id:
                try:
                    attribute_value = AttributeValue.objects.get(id=attribute_value_id)
                    ProductAttribute.objects.create(
                        product=product,
                        attribute_value=attribute_value
                    )
                except AttributeValue.DoesNotExist:
                    logger.warning(f"Атрибут с ID {attribute_value_id} не найден")

    @swagger_auto_schema(
        operation_description="Сканировать штрих-код и получить информацию о товаре",
        manual_parameters=[
            openapi.Parameter(
                'barcode',
                openapi.IN_QUERY,
                description="Штрих-код для сканирования",
                type=openapi.TYPE_STRING,
                required=True
            )
        ]
    )
    @action(detail=False, methods=['get'])
    def scan_barcode(self, request):
        """Сканирование штрих-кода - ищет только в текущем магазине"""
        barcode = request.query_params.get('barcode')
        if not barcode:
            return Response(
                {'error': _('Штрих-код не указан')},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ✅ ИСПРАВЛЕНИЕ: Используем get_current_store() как в других методах
        current_store = self.get_current_store()

        if not current_store:
            return Response({
                'error': 'Магазин не определен. Переавторизуйтесь или выберите магазин.',
                'debug_info': {
                    'user': request.user.username,
                    'has_current_store': hasattr(request.user, 'current_store'),
                    'current_store_value': getattr(request.user, 'current_store', None)
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ ИСПРАВЛЕНИЕ: Добавляем логирование для отладки
        logger.info(f"🔍 Scanning barcode: '{barcode}' in store: {current_store.name} (ID: {current_store.id})")

        # Ищем товар в текущем магазине
        product = Product.objects.filter(
            store=current_store,
            barcode=barcode
        ).select_related('category', 'stock').first()

        # ✅ ИСПРАВЛЕНИЕ: Дополнительная отладочная информация
        if not product:
            # Проверяем, есть ли товар с таким штрих-кодом в других магазинах
            other_stores_count = Product.objects.filter(barcode=barcode).exclude(store=current_store).count()
            all_products_count = Product.objects.filter(barcode=barcode).count()

            logger.warning(f"❌ Product not found. Barcode: '{barcode}', Current store: {current_store.id}, "
                          f"Products with this barcode in other stores: {other_stores_count}, "
                          f"Total products with this barcode: {all_products_count}")

        if product:
            logger.info(f"✅ Product found: {product.name} (ID: {product.id})")
            serializer = self.get_serializer(product)
            return Response({
                'found': True,
                'product': serializer.data,
                'message': _('Товар найден')
            })
        else:
            # Товар не найден, возвращаем категории текущего магазина
            categories = ProductCategory.objects.filter(store=current_store)

            return Response({
                'found': False,
                'barcode': barcode,
                'categories': ProductCategorySerializer(categories, many=True).data,
                'message': _('Товар не найден. Создайте новый товар.'),
                'debug_info': {
                    'current_store_id': current_store.id,
                    'current_store_name': current_store.name,
                    'barcode_searched': barcode
                }
            })

    @action(detail=True, methods=['post'])
    def sell(self, request, pk=None):
        """
        Продажа товара (списание со склада)
        """
        product = self.get_object()
        quantity = request.data.get('quantity', 0)

        if quantity <= 0:
            return Response(
                {'error': _('Количество должно быть больше нуля')},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                product.stock.sell(quantity)

            return Response({
                'message': _('Товар успешно продан'),
                'sold_quantity': quantity,
                'remaining_stock': product.stock.quantity
            })
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """
        Получить товары с низким остатком
        """
        min_quantity = int(request.query_params.get('min_quantity', 10))
        products = self.get_queryset().filter(stock__quantity__lte=min_quantity)

        serializer = self.get_serializer(products, many=True)
        return Response({
            'products': serializer.data,
            'count': products.count(),
            'min_quantity': min_quantity
        })

    @action(detail=False, methods=['get'])
    def product_sizes_info(self, request):
        """
        Получить информацию о размерах и количестве товаров по имени

        Query Parameters:
            - name: название товара (или его часть)

        Returns:
            - Если name передан: информация о товарах с этим именем, их размерах и количестве
            - Если name не передан: пустой JSON {}

        Example:
            GET /api/inventory/products/product_sizes_info/?name=Футболка

        Response:
            {
                "product_name": "Футболка",
                "total_products": 5,
                "total_stock": 150,
                "sizes": [
                    {
                        "size": "S",
                        "size_id": 1,
                        "count": 1,
                        "stock_quantity": 20,
                        "products": [
                            {
                                "id": 1,
                                "name": "Футболка - S",
                                "barcode": "123456789",
                                "stock": 20,
                                "price": 150000.00
                            }
                        ]
                    },
                    {
                        "size": "M",
                        "size_id": 2,
                        "count": 2,
                        "stock_quantity": 50,
                        "products": [...]
                    }
                ],
                "products_without_size": {
                    "count": 1,
                    "stock_quantity": 30,
                    "products": [...]
                }
            }
        """
        # Получаем параметр name из запроса
        product_name = request.query_params.get('name', '').strip()

        # Если name не передан или пустой - возвращаем пустой JSON
        if not product_name:
            return Response({})

        # Получаем текущий магазин
        current_store = self.get_current_store()
        if not current_store:
            return Response({
                'error': 'Магазин не определен'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Ищем товары по имени (частичное совпадение, регистронезависимо)
        products = Product.objects.filter(
            store=current_store,
            name__icontains=product_name
        ).select_related('size', 'stock', 'category').order_by('name', 'size__size')

        # Если товары не найдены
        if not products.exists():
            return Response({
                'product_name': product_name,
                'total_products': 0,
                'total_stock': 0,
                'sizes': [],
                'message': f'Товары с названием "{product_name}" не найдены'
            })

        # Группируем товары по размерам
        sizes_data = {}
        products_without_size = []
        total_stock = 0

        for product in products:
            stock_quantity = product.stock.quantity if hasattr(product, 'stock') else 0
            total_stock += stock_quantity

            product_info = {
                'id': product.id,
                'name': product.name,
                'barcode': product.barcode,
                'stock': stock_quantity,
                'price': float(product.sale_price),
                'category': product.category.name if product.category else None
            }

            if product.size:
                size_key = product.size.size
                if size_key not in sizes_data:
                    sizes_data[size_key] = {
                        'size': product.size.size,
                        'size_id': product.size.id,
                        'chest': product.size.chest,
                        'waist': product.size.waist,
                        'length': product.size.length,
                        'count': 0,
                        'stock_quantity': 0,
                        'products': []
                    }

                sizes_data[size_key]['count'] += 1
                sizes_data[size_key]['stock_quantity'] += stock_quantity
                sizes_data[size_key]['products'].append(product_info)
            else:
                products_without_size.append(product_info)

        # Преобразуем словарь размеров в список и сортируем
        size_order = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
        sizes_list = list(sizes_data.values())

        # Сортируем размеры в правильном порядке
        def size_sort_key(item):
            try:
                return size_order.index(item['size'])
            except ValueError:
                return 999  # Неизвестные размеры в конец

        sizes_list.sort(key=size_sort_key)

        # Формируем результат
        response_data = {
            'product_name': product_name,
            'total_products': products.count(),
            'total_stock': total_stock,
            'sizes': sizes_list
        }

        # Добавляем информацию о товарах без размера, если они есть
        if products_without_size:
            response_data['products_without_size'] = {
                'count': len(products_without_size),
                'stock_quantity': sum(p['stock'] for p in products_without_size),
                'products': products_without_size
            }

        return Response(response_data)


    @action(detail=False, methods=['get'])
    def sizes_summary(self, request):
        """
        Получить сводку по всем размерам в магазине
        Более простой вариант - только общая статистика

        Query Parameters:
            - name: (опционально) фильтр по имени товара

        Example:
            GET /api/inventory/products/sizes_summary/
            GET /api/inventory/products/sizes_summary/?name=Футболка
        """
        product_name = request.query_params.get('name', '').strip()

        # Если имя не указано - возвращаем пустой JSON
        if not product_name:
            return Response({})

        # Получаем текущий магазин
        current_store = self.get_current_store()
        if not current_store:
            return Response({
                'error': 'Магазин не определен'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Базовый queryset
        queryset = Product.objects.filter(store=current_store)

        # Фильтруем по имени если указано
        if product_name:
            queryset = queryset.filter(name__icontains=product_name)

        # Агрегируем данные по размерам
        from django.db.models import Count, Sum, Avg

        sizes_stats = queryset.filter(
            size__isnull=False
        ).values(
            'size__size'
        ).annotate(
            product_count=Count('id'),
            total_stock=Sum('stock__quantity'),
            avg_price=Avg('sale_price'),
            min_price=models.Min('sale_price'),
            max_price=models.Max('sale_price')
        ).order_by('size__size')

        # Преобразуем в список и сортируем
        size_order = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
        sizes_list = list(sizes_stats)

        def size_sort_key(item):
            try:
                return size_order.index(item['size__size'])
            except (ValueError, KeyError):
                return 999

        sizes_list.sort(key=size_sort_key)

        # Общая статистика
        total_stats = queryset.aggregate(
            total_products=Count('id'),
            total_with_size=Count('id', filter=models.Q(size__isnull=False)),
            total_without_size=Count('id', filter=models.Q(size__isnull=True)),
            total_stock=Sum('stock__quantity')
        )

        return Response({
            'filter': {'name': product_name} if product_name else None,
            'summary': total_stats,
            'by_size': sizes_list
        })


    @action(detail=False, methods=['post'])
    def check_sizes(self, request):
        """
        Проверить наличие размеров для списка товаров

        Body:
            {
                "product_names": ["Футболка", "Джинсы", "Платье"]
            }

        Returns:
            Информация о размерах для каждого товара
        """
        product_names = request.data.get('product_names', [])

        if not product_names:
            return Response({})

        # Получаем текущий магазин
        current_store = self.get_current_store()
        if not current_store:
            return Response({
                'error': 'Магазин не определен'
            }, status=status.HTTP_400_BAD_REQUEST)

        result = {}

        for name in product_names:
            if not name or not name.strip():
                continue

            name = name.strip()

            # Находим товары с этим именем
            products = Product.objects.filter(
                store=current_store,
                name__icontains=name
            ).select_related('size', 'stock')

            if not products.exists():
                result[name] = {
                    'found': False,
                    'total_products': 0,
                    'sizes': []
                }
                continue

            # Собираем уникальные размеры
            sizes = set()
            total_stock = 0

            for product in products:
                if product.size:
                    sizes.add(product.size.size)
                if hasattr(product, 'stock'):
                    total_stock += product.stock.quantity

            # Сортируем размеры
            size_order = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
            sorted_sizes = sorted(
                list(sizes),
                key=lambda x: size_order.index(x) if x in size_order else 999
            )

            result[name] = {
                'found': True,
                'total_products': products.count(),
                'total_stock': total_stock,
                'available_sizes': sorted_sizes,
                'has_products_without_size': products.filter(size__isnull=True).exists()
            }

        return Response(result)


class ProductBatchViewSet(StoreViewSetMixin, ModelViewSet):
    """
    ViewSet для управления партиями товаров
    """
    serializer_class = ProductBatchSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductBatchFilter
    filterset_fields = ['product', 'supplier']
    search_fields = ['product__name', 'supplier']
    ordering_fields = ['created_at', 'expiration_date', 'quantity']
    ordering = ['expiration_date', 'created_at']

    def get_queryset(self):
        return ProductBatch.objects.select_related('product').all()

    @swagger_auto_schema(
        operation_description="Создать новую партию товара",
        request_body=ProductBatchSerializer,
        responses={201: ProductBatchSerializer}
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            batch = serializer.save()
            logger.info(f"Создана партия: {batch}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        """
        Партии с истекающим сроком годности
        """
        from datetime import date, timedelta

        days = int(request.query_params.get('days', 7))
        expiry_date = date.today() + timedelta(days=days)

        batches = self.get_queryset().filter(
            expiration_date__lte=expiry_date,
            expiration_date__isnull=False
        )

        serializer = self.get_serializer(batches, many=True)
        return Response({
            'batches': serializer.data,
            'count': batches.count(),
            'expiring_within_days': days
        })


class StockViewSet(StoreViewSetMixin, ModelViewSet):
    """
    ViewSet для управления остатками на складе
    """
    serializer_class = StockSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StockFilter
    search_fields = ['product__name', 'product__barcode']
    filterset_fields = ['product__category']
    ordering_fields = ['quantity', 'updated_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        return Stock.objects.select_related('product', 'product__category').all()

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Сводка по остаткам на складе
        """
        total_products = self.get_queryset().count()
        total_quantity = self.get_queryset().aggregate(
            total=Sum('quantity')
        )['total'] or 0

        low_stock_count = self.get_queryset().filter(quantity__lte=10).count()
        zero_stock_count = self.get_queryset().filter(quantity=0).count()

        return Response({
            'total_products': total_products,
            'total_quantity': total_quantity,
            'low_stock_products': low_stock_count,
            'out_of_stock_products': zero_stock_count
        })

    @action(detail=True, methods=['post'])
    def adjust(self, request, pk=None):
        """
        Корректировка остатков
        """
        stock = self.get_object()
        new_quantity = request.data.get('quantity')
        reason = request.data.get('reason', 'Корректировка')

        if new_quantity is None or new_quantity < 0:
            return Response(
                {'error': _('Некорректное количество')},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_quantity = stock.quantity
        stock.quantity = new_quantity
        stock.save()

        logger.info(
            f"Корректировка остатков {stock.product.name}: "
            f"{old_quantity} -> {new_quantity}. Причина: {reason}"
        )

        return Response({
            'message': _('Остатки скорректированы'),
            'old_quantity': old_quantity,
            'new_quantity': new_quantity,
            'reason': reason
        })

class SizeInfoViewSet(ModelViewSet):
    """
    ViewSet для работы с размерной информацией
    Поддерживает фильтрацию, поиск, сортировку и опциональную пагинацию
    """
    serializer_class = SizeInfoSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SizeInfoFilter  # Используем кастомный фильтр
    search_fields = ['size']  # Поиск по размеру
    ordering_fields = ['size', 'chest', 'waist', 'length']  # Поля для сортировки
    ordering = ['size']  # Сортировка по умолчанию
    pagination_class = OptionalPagination  # Опциональная пагинация

    def get_queryset(self):
        """
        Возвращает queryset с оптимизацией
        """
        return SizeInfo.objects.all().select_related()

    def get_pagination_params(self, request):
        """
        Извлекает параметры пагинации из запроса
        """
        try:
            limit = int(request.query_params.get('limit', 20))
            offset = int(request.query_params.get('offset', 0))

            # Ограничиваем максимальный limit
            if limit > 100:
                limit = 100
            elif limit <= 0:
                limit = 20

            if offset < 0:
                offset = 0

            return limit, offset
        except (ValueError, TypeError):
            return 20, 0

    @swagger_auto_schema(
        operation_description="Получить список размерной информации. Если не указаны параметры limit/offset - возвращает все записи без пагинации.",
        manual_parameters=[
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description="[ОПЦИОНАЛЬНО] Количество записей на странице (по умолчанию 20, максимум 100). Если не указан - возвращает все записи.",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'offset',
                openapi.IN_QUERY,
                description="[ОПЦИОНАЛЬНО] Смещение от начала списка. Работает только вместе с limit.",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'size',
                openapi.IN_QUERY,
                description="Фильтр по размеру (можно указать несколько через запятую)",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'chest_min',
                openapi.IN_QUERY,
                description="Минимальный обхват груди",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'chest_max',
                openapi.IN_QUERY,
                description="Максимальный обхват груди",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'waist_min',
                openapi.IN_QUERY,
                description="Минимальный обхват талии",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'waist_max',
                openapi.IN_QUERY,
                description="Максимальный обхват талии",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'length_min',
                openapi.IN_QUERY,
                description="Минимальная длина",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'length_max',
                openapi.IN_QUERY,
                description="Максимальная длина",
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description="Поиск по размеру",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'ordering',
                openapi.IN_QUERY,
                description="Сортировка (size, chest, waist, length). Для убывания добавьте '-'",
                type=openapi.TYPE_STRING
            ),
        ],
        responses={200: SizeInfoSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        """
        Получить список размерной информации с поддержкой:
        - опциональной offset/limit пагинации
        - фильтрации по всем полям
        - поиска по размеру
        - сортировки

        Если не указаны параметры limit/offset - возвращает все записи
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Логируем параметры запроса для отладки
        logger.info(f"SizeInfo list request - query_params: {dict(request.query_params)}")

        # Пагинация работает автоматически через OptionalPagination
        page = self.paginate_queryset(queryset)

        if page is not None:
            # Есть пагинация - возвращаем страницу
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # Нет пагинации - возвращаем все записи
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': queryset.count(),
            'results': serializer.data
        })

    @swagger_auto_schema(
        operation_description="Создать новую размерную информацию",
        request_body=SizeInfoSerializer,
        responses={
            201: SizeInfoSerializer,
            400: 'Ошибка валидации'
        }
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Создание новой размерной информации
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            size_info = serializer.save()
            logger.info(f"Создана размерная информация: {size_info.size}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        logger.warning(f"Ошибка валидации при создании размерной информации: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Обновить размерную информацию",
        request_body=SizeInfoSerializer,
        responses={
            200: SizeInfoSerializer,
            400: 'Ошибка валидации',
            404: 'Размерная информация не найдена'
        }
    )
    def update(self, request, *args, **kwargs):
        """
        Обновление размерной информации
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            size_info = serializer.save()
            logger.info(f"Обновлена размерная информация: {size_info.size}")
            return Response(serializer.data)

        logger.warning(f"Ошибка валидации при обновлении размерной информации: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Дополнительные утилитные views

class InventoryStatsView(generics.GenericAPIView):
    """
    Общая статистика по складу
    """

    @swagger_auto_schema(
        operation_description="Получить общую статистику по складу",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'total_products': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'total_categories': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'total_stock_value': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'low_stock_alerts': openapi.Schema(type=openapi.TYPE_INTEGER),
                }
            )
        }
    )
    def get(self, request):
        stats = {
            'total_products': Product.objects.count(),
            'total_categories': ProductCategory.objects.count(),
            'total_attributes': AttributeType.objects.count(),
            'total_stock_quantity': Stock.objects.aggregate(
                total=Sum('quantity')
            )['total'] or 0,
            'low_stock_alerts': Stock.objects.filter(quantity__lte=10).count(),
            'out_of_stock': Stock.objects.filter(quantity=0).count(),
            'total_batches': ProductBatch.objects.count(),
        }

        # Подсчет общей стоимости склада
        from django.db.models import F
        total_value = ProductBatch.objects.aggregate(
            total=Sum(F('quantity') * F('purchase_price'))
        )['total'] or 0
        stats['total_stock_value'] = float(total_value)

        return Response(stats)



from django.http import FileResponse, HttpResponseNotFound
from django.views.decorators.csrf import csrf_exempt
import os

from .models import Product
from django.conf import settings

@csrf_exempt
def product_label_proxy(request, pk):
    """
    Отдаёт картинку товара через прокси с CORS-заголовками
    """
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return HttpResponseNotFound("Product not found")

    if not product.image_label:
        return HttpResponseNotFound("Image not found")

    file_path = os.path.join(settings.MEDIA_ROOT, str(product.image_label))

    if not os.path.exists(file_path):
        return HttpResponseNotFound("File not found")

    response = FileResponse(open(file_path, "rb"), content_type="image/png")
    response["Access-Control-Allow-Origin"] = "*"   # 🔑 главное!
    return response