# inventory/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.decorators import action
from django.db.models import Q
from django.db.models import F
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from .models import Product, ProductCategory, Stock, ProductBatch, UnitOfMeasure, MeasurementCategory
from .serializers import (
    ProductSerializer, 
    ProductCategorySerializer, 
    StockSerializer, 
    ProductBatchSerializer, 
    SaleSerializer,
    UnitOfMeasureSerializer,
    MeasurementCategorySerializer, 
    MeasurementCategoryDetailSerializer,
    UnitOfMeasureSerializer, 
    UnitOfMeasureDetailSerializer,
    UnitConversionSerializer,
    UnitConversionResultSerializer
)

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

logger = logging.getLogger('inventory')

class IsStockkeeperOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name__in=['admin', 'stockkeeper']).exists()
    
class BaseInventoryView(APIView):
    """Базовый класс для всех вьюшек инвентаря"""
    
    def handle_exception(self, exc):
        logger.error(f"[SomPOS] Error in {self.__class__.__name__}: {str(exc)}", 
                    exc_info=True)
        return super().handle_exception(exc)



class MeasurementCategoryViewSet(viewsets.ModelViewSet):
    queryset = MeasurementCategory.objects.prefetch_related('units').all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'id']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action in ['retrieve']:
            return MeasurementCategoryDetailSerializer
        return MeasurementCategorySerializer

    @swagger_auto_schema(
        operation_summary="Список категорий единиц измерения",
        responses={200: MeasurementCategorySerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Создать категорию единиц измерения",
        request_body=MeasurementCategorySerializer,
        responses={201: MeasurementCategorySerializer}
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)


class UnitOfMeasureViewSet(viewsets.ModelViewSet):
    queryset = UnitOfMeasure.objects.select_related('category').all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'short_name']
    ordering_fields = ['name', 'created_at']
    filterset_fields = ['category', 'is_active']

    def get_serializer_class(self):
        if self.action in ['retrieve']:
            return UnitOfMeasureDetailSerializer
        return UnitOfMeasureSerializer

    @swagger_auto_schema(
        operation_summary="Список единиц измерения",
        responses={200: UnitOfMeasureSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Создать единицу измерения",
        request_body=UnitOfMeasureSerializer,
        responses={201: UnitOfMeasureSerializer}
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        method='post',
        operation_summary="Конвертировать значение между единицами",
        request_body=UnitConversionSerializer,
        responses={200: UnitConversionResultSerializer}
    )
    @action(detail=False, methods=['post'], url_path='convert')
    def convert_units(self, request):
        """Конвертация между единицами измерения"""
        serializer = UnitConversionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from_unit = serializer.validated_data['from_unit']
        to_unit = serializer.validated_data['to_unit']
        value = serializer.validated_data['value']

        # Формула: value * (to_factor / from_factor)
        converted = value * (to_unit.conversion_factor / from_unit.conversion_factor)

        result = {
            'original_value': value,
            'converted_value': round(converted, 6),
            'from_unit': from_unit,
            'to_unit': to_unit,
            'conversion_formula': f"{value} * ({to_unit.conversion_factor} / {from_unit.conversion_factor})"
        }
        return Response(UnitConversionResultSerializer(result).data)

class ProductCategoryCreateView(BaseInventoryView):

    @swagger_auto_schema(
        operation_summary="Создать категорию товара",
        operation_description="Создает новую категорию для товаров",
        request_body=ProductCategorySerializer,
        responses={
            201: ProductCategorySerializer,
            400: "Невалидные данные"
        },
        tags=['Категории']
    )

    def post(self, request):
        serializer = ProductCategorySerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Invalid category data: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        category = serializer.save()
        logger.info(f"Created category: {category.name} (ID: {category.id})")
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductCategoryListView(BaseInventoryView):

    @swagger_auto_schema(
        operation_summary="Список категорий",
        operation_description="Возвращает все категории товаров",
        responses={200: ProductCategorySerializer(many=True)},
        tags=['Категории']
    )

    def get(self, request):
        categories = ProductCategory.objects.all().order_by('name')
        serializer = ProductCategorySerializer(categories, many=True)
        logger.debug(f"Returned {len(categories)} categories")
        return Response(serializer.data)


class ProductCreateView(BaseInventoryView):

    @swagger_auto_schema(
        operation_summary="Создать товар",
        operation_description="Добавляет новый товар в систему",
        request_body=ProductSerializer,
        responses={
            201: ProductSerializer,
            400: "Невалидные данные"
        },
        tags=['Товары']
    )
    
    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Invalid product data: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        product = serializer.save()
        logger.info(f"Created product: {product.name} (ID: {product.id})")
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductListView(BaseInventoryView):

    @swagger_auto_schema(
        operation_summary="Список товаров",
        operation_description="Возвращает все товары с пагинацией",
        manual_parameters=[
            openapi.Parameter('page', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('page_size', openapi.IN_QUERY, type=openapi.TYPE_INTEGER)
        ],
        responses={200: ProductSerializer(many=True)},
        tags=['Товары']
    )

    def get(self, request):
        products = Product.objects.select_related('category').order_by('name')
        serializer = ProductSerializer(products, many=True)
        logger.debug(f"Returned {len(products)} products")
        return Response(serializer.data)


class ProductSearchView(BaseInventoryView):

    @swagger_auto_schema(
        operation_summary="Поиск товаров",
        operation_description="Поиск товаров по названию или штрихкоду",
        manual_parameters=[
            openapi.Parameter('q', openapi.IN_QUERY, description="Поисковый запрос", 
                            type=openapi.TYPE_STRING, required=True)
        ],
        responses={200: ProductSerializer(many=True)},
        tags=['Товары', 'Поиск']
    )

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response(
                {"error": _("Search query is required")},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(barcode__icontains=query)
        ).select_related('category')[:50]  # Лимит результатов
        
        serializer = ProductSerializer(products, many=True)
        logger.info(f"Search for '{query}' returned {len(products)} products")
        return Response({
            'query': query,
            'results': serializer.data,
            'count': len(products)
        })


class ProductBarcodeLookupView(BaseInventoryView):

    @swagger_auto_schema(
        operation_summary="Поиск по штрихкоду",
        operation_description="Поиск товара по штрихкоду",
        manual_parameters=[
            openapi.Parameter('barcode', openapi.IN_QUERY, 
                            description="Штрихкод товара", 
                            type=openapi.TYPE_STRING, required=True)
        ],
        responses={
            200: ProductSerializer,
            404: "Товар не найден",
            400: "Не указан штрихкод"
        },
        tags=['Товары', 'Поиск']
    )

    def get(self, request):
        barcode = request.query_params.get('barcode', '').strip()
        if not barcode:
            return Response(
                {"error": _("Barcode is required")},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            product = Product.objects.filter(barcode=barcode).first()
            if not product:
                logger.debug(f"No product found for barcode: {barcode}")
                return Response(
                    {"message": _("Product not found")},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            serializer = ProductSerializer(product)
            logger.info(f"Found product {product.id} for barcode: {barcode}")
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Barcode lookup error: {str(e)}")
            return Response(
                {"error": _("Internal server error")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StockManagementView(BaseInventoryView):

    @swagger_auto_schema(
        auto_schema=None,
        operation_summary="Обновление остатков",
        operation_description="Ручное изменение количества товара на складе",
        request_body=StockSerializer,
        responses={
            200: StockSerializer,
            400: "Невалидные данные",
            404: "Товар не найден"
        }
    )
    @transaction.atomic
    def post(self, request):
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity')
        
        if not product_id or not quantity:
            return Response(
                {"error": _("product_id and quantity are required")},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            stock = Stock.objects.select_for_update().get(product_id=product_id)
            stock.quantity += int(quantity)
            if stock.quantity < 0:
                raise ValueError(_("Stock cannot be negative"))
                
            stock.save()
            logger.info(
                f"Updated stock for product {product_id}. "
                f"Change: {quantity}, New quantity: {stock.quantity}"
            )
            return Response(StockSerializer(stock).data)
            
        except Stock.DoesNotExist:
            return Response(
                {"error": _("Product not found")},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class ProductBatchCreateView(BaseInventoryView):

    @swagger_auto_schema(
        operation_summary="Добавить партию",
        operation_description="Добавляет новую партию товара на склад",
        request_body=ProductBatchSerializer,
        responses={
            201: ProductBatchSerializer,
            400: "Невалидные данные"
        },
        tags=['Склад']
    )

    @transaction.atomic
    def post(self, request):
        serializer = ProductBatchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        batch = serializer.save()
        logger.info(
            f"Created batch {batch.id} for product {batch.product_id}. "
            f"Quantity: {batch.quantity}, Expires: {batch.expiration_date}"
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# class ProductScanView(APIView):
#     @swagger_auto_schema(
#         operation_summary="Сканирование товара",
#         operation_description="Сканирование штрихкода с автоматическим созданием товара или добавлением партии",
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             properties={
#                 'barcode': openapi.Schema(type=openapi.TYPE_STRING, description='Штрихкод товара'),
#                 'name': openapi.Schema(type=openapi.TYPE_STRING, description='Название товара'),
#                 'category': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID категории'),
#                 'sale_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Цена продажи'),
#                 'quantity': openapi.Schema(type=openapi.TYPE_INTEGER, description='Количество в партии', default=1),
#                 'expiration_date': openapi.Schema(type=openapi.TYPE_STRING, format='date', description='Срок годности (YYYY-MM-DD)', nullable=True),
#                 'supplier': openapi.Schema(type=openapi.TYPE_STRING, description='Поставщик', nullable=True),
#                 'purchase_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Цена закупки', nullable=True),
#                 'unit': openapi.Schema(type=openapi.TYPE_STRING, description='Единица измерения (piece, kg, liter, pack)', default='piece')
#             },
#             required=['barcode', 'name', 'category', 'sale_price', 'quantity']
#         ),
#         responses={
#             200: openapi.Response('Товар существует, партия добавлена/обновлена', ProductSerializer),
#             201: openapi.Response('Товар создан', ProductSerializer),
#             400: openapi.Response('Невалидные данные')
#         },
#         tags=['Товары', 'Сканирование']
#     )
#     @transaction.atomic
#     def post(self, request):
#         barcode = request.data.get('barcode', '').strip()
#         if not barcode:
#             return Response(
#                 {"error": _("Штрихкод обязателен")},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         # Проверяем существующий товар
#         product = Product.objects.filter(barcode=barcode).first()
#         if product:
#             # Обновляем данные товара, если нужно
#             product_data = {
#                 'name': request.data.get('name'),
#                 'category': request.data.get('category'),
#                 'sale_price': request.data.get('sale_price'),
#                 'unit': request.data.get('unit', 'piece')
#             }
#             product_serializer = ProductSerializer(product, data=product_data, partial=True)
#             if not product_serializer.is_valid():
#                 return Response(product_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#             product = product_serializer.save()

#             # Проверяем существующую партию с таким же сроком годности и поставщиком
#             supplier = request.data.get('supplier', '')
#             expiration_date = request.data.get('expiration_date')
#             batch_query = ProductBatch.objects.filter(
#                 product=product,
#                 expiration_date=expiration_date,
#                 supplier=supplier
#             )
#             if batch_query.exists():
#                 batch = batch_query.first()
#                 batch.quantity = F('quantity') + request.data.get('quantity', 1)
#                 batch.save(update_fields=['quantity'])
#                 batch.refresh_from_db(fields=['quantity'])
#                 batch_serializer = ProductBatchSerializer(batch)
#                 logger.info(
#                     f"Updated batch {batch.id} for product {product.id}. "
#                     f"New quantity: {batch.quantity}"
#                 )
#             else:
#                 batch_data = {
#                     'product': product.id,
#                     'quantity': request.data.get('quantity', 1),
#                     'expiration_date': expiration_date,
#                     'supplier': supplier,
#                     'purchase_price': request.data.get('purchase_price')
#                 }
#                 batch_serializer = ProductBatchSerializer(data=batch_data)
#                 if not batch_serializer.is_valid():
#                     return Response(batch_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#                 batch = batch_serializer.save()
#                 logger.info(
#                     f"Created new batch {batch.id} for product {product.id}. "
#                     f"Quantity: {batch.quantity}"
#                 )

#             return Response(
#                 {
#                     "exists": True,
#                     "message": _("Товар существует, партия добавлена/обновлена"),
#                     "product": ProductSerializer(product).data,
#                     "batch": batch_serializer.data
#                 },
#                 status=status.HTTP_200_OK
#             )

#         # Создаём новый товар
#         product_data = {
#             'barcode': barcode,
#             'name': request.data.get('name'),
#             'category': request.data.get('category'),
#             'sale_price': request.data.get('sale_price'),
#             'unit': request.data.get('unit', 'piece')
#         }
#         product_serializer = ProductSerializer(data=product_data)
#         if not product_serializer.is_valid():
#             return Response(product_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#         product = product_serializer.save()

#         # Создаём партию
#         batch_data = {
#             'product': product.id,
#             'quantity': request.data.get('quantity', 1),
#             'expiration_date': request.data.get('expiration_date'),
#             'supplier': request.data.get('supplier', ''),
#             'purchase_price': request.data.get('purchase_price')
#         }
#         batch_serializer = ProductBatchSerializer(data=batch_data)
#         if not batch_serializer.is_valid():
#             return Response(batch_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#         batch = batch_serializer.save()

#         logger.info(
#             f"Created new product {product.id} from scan. "
#             f"Batch: {batch.quantity} units"
#         )
#         return Response(
#             {
#                 "exists": False,
#                 "message": _("Товар создан"),
#                 "product": product_serializer.data,
#                 "batch": batch_serializer.data
#             },
#             status=status.HTTP_201_CREATED
#         )
class ProductScanView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsStockkeeperOrAdmin]

    # @swagger_auto_schema(
    #     auto_schema=None,
    #     operation_summary="Сканирование товара",
    #     operation_description="Сканирование штрихкода или создание товара без штрихкода с добавлением партии",
    #     request_body=openapi.Schema(
    #         type=openapi.TYPE_OBJECT,
    #         properties={
    #             'barcode': openapi.Schema(type=openapi.TYPE_STRING, description='Штрихкод товара (необязательный)', nullable=True),
    #             'name': openapi.Schema(type=openapi.TYPE_STRING, description='Название товара'),
    #             'category': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID категории'),
    #             'sale_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Цена продажи'),
    #             'quantity': openapi.Schema(type=openapi.TYPE_INTEGER, description='Количество в партии', default=1),
    #             'expiration_date': openapi.Schema(type=openapi.TYPE_STRING, format='date', description='Срок годности (YYYY-MM-DD)', nullable=True),
    #             'supplier': openapi.Schema(type=openapi.TYPE_STRING, description='Поставщик', nullable=True),
    #             'purchase_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Цена закупки', nullable=True),
    #             'unit': openapi.Schema(type=openapi.TYPE_STRING, description='Единица измерения (piece, kg, liter, pack)', default='piece')
    #         },
    #         required=['name', 'category', 'sale_price', 'quantity']
    #     ),
    #     responses={
    #         200: openapi.Response('Товар существует, партия добавлена/обновлена', ProductSerializer),
    #         201: openapi.Response('Товар создан', ProductSerializer),
    #         400: openapi.Response('Невалидные данные')
    #     },
    #     tags=['Товары', 'Сканирование'],
    #     security=[{'Bearer': []}]
    # )
    @transaction.atomic
    def post(self, request):
        barcode = request.data.get('barcode', '').strip() or None
        name = request.data.get('name')
        category_id = request.data.get('category')
        sale_price = request.data.get('sale_price')
        quantity = request.data.get('quantity', 1)
        expiration_date = request.data.get('expiration_date')
        supplier = request.data.get('supplier', '')
        unit = request.data.get('unit', 'piece')

        if not all([name, category_id, sale_price, quantity]):
            return Response(
                {"error": _("Поля name, category, sale_price, quantity обязательны")},
                status=status.HTTP_400_BAD_REQUEST
            )

        product = None
        if barcode:
            product = Product.objects.filter(barcode=barcode).first()
        if not product:
            product = Product.objects.filter(name=name, category_id=category_id).first()

        if product:
            product_data = {
                'name': name,
                'category': category_id,
                'sale_price': sale_price,
                'unit': unit,
                'barcode': barcode
            }
            product_serializer = ProductSerializer(product, data=product_data, partial=True)
            if not product_serializer.is_valid():
                return Response(product_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            product = product_serializer.save()

            batch_query = ProductBatch.objects.filter(
                product=product,
                expiration_date=expiration_date,
                supplier=supplier
            )
            if batch_query.exists():
                batch = batch_query.first()
                batch.quantity = F('quantity') + quantity
                batch.save(update_fields=['quantity'])
                batch_serializer = ProductBatchSerializer(batch)
                logger.info(
                    f"Updated batch {batch.id} for product {product.id} by {request.user.username}. "
                    f"New quantity: {batch.quantity}"
                )
            else:
                batch_data = {
                    'product': product.id,
                    'quantity': quantity,
                    'expiration_date': expiration_date,
                    'supplier': supplier,
                    'purchase_price': request.data.get('purchase_price')
                }
                batch_serializer = ProductBatchSerializer(data=batch_data)
                if not batch_serializer.is_valid():
                    return Response(batch_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                batch = batch_serializer.save()
                logger.info(
                    f"Created new batch {batch.id} for product {product.id} by {request.user.username}. "
                    f"Quantity: {batch.quantity}"
                )

            return Response(
                {
                    "exists": True,
                    "message": _("Товар существует, партия добавлена/обновлена"),
                    "product": ProductSerializer(product).data,
                    "batch": batch_serializer.data
                },
                status=status.HTTP_200_OK
            )

        product_data = {
            'barcode': barcode,
            'name': name,
            'category': category_id,
            'sale_price': sale_price,
            'unit': unit
        }
        product_serializer = ProductSerializer(data=product_data)
        if not product_serializer.is_valid():
            return Response(product_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        product = product_serializer.save()

        batch_data = {
            'product': product.id,
            'quantity': quantity,
            'expiration_date': expiration_date,
            'supplier': supplier,
            'purchase_price': request.data.get('purchase_price')
        }
        batch_serializer = ProductBatchSerializer(data=batch_data)
        if not batch_serializer.is_valid():
            return Response(batch_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        batch = batch_serializer.save()

        logger.info(
            f"Created new product {product.id} by {request.user.username}. "
            f"Batch: {batch.quantity} units"
        )
        return Response(
            {
                "exists": False,
                "message": _("Товар создан"),
                "product": product_serializer.data,
                "batch": batch_serializer.data
            },
            status=status.HTTP_201_CREATED
        )

class SaleProcessingView(BaseInventoryView):

    @swagger_auto_schema(
        operation_summary="Оформление продажи",
        operation_description="Проведение продажи товара со списанием со склада",
        request_body=SaleSerializer,
        responses={
            200: openapi.Response('Успешная продажа', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'product_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'quantity_sold': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'remaining_stock': openapi.Schema(type=openapi.TYPE_INTEGER)
                }
            )),
            400: "Невалидные данные",
            404: "Товар не найден"
        },
        tags=['Продажи']
    )
    
    @transaction.atomic
    def post(self, request):
        serializer = SaleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        product_id = serializer.validated_data['product_id']
        quantity = serializer.validated_data['quantity']
        
        try:
            stock = Stock.objects.select_for_update().get(product_id=product_id)
            stock.sell(quantity)
            
            logger.info(
                f"Processed sale for product {product_id}. "
                f"Sold: {quantity}, Remaining: {stock.quantity}"
            )
            
            return Response({
                "product_id": product_id,
                "quantity_sold": quantity,
                "remaining_stock": stock.quantity,
                "message": _("Sale processed successfully")
            })
            
        except Stock.DoesNotExist:
            return Response(
                {"error": _("Product not found")},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
class StockkeeperProductAddView(APIView):
    def post(self, request):
        # Данные от складчика
        barcode = request.data.get('barcode')
        name = request.data.get('name')
        category_id = request.data.get('category_id')
        sale_price = request.data.get('sale_price')
        quantity = request.data.get('quantity')
        expiration_date = request.data.get('expiration_date')
        supplier = request.data.get('supplier', '')
        unit = request.data.get('unit', 'piece')

        # Валидация обязательных полей
        if not all([barcode, name, category_id, sale_price, quantity]):
            return Response(
                {"error": "Все поля (barcode, name, category_id, sale_price, quantity) обязательны"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Проверка категории
        try:
            ProductCategory.objects.get(id=category_id)
        except ProductCategory.DoesNotExist:
            return Response(
                {"error": "Категория не найдена"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Проверка и создание/обновление товара
        product_data = {
            "name": name,
            "barcode": barcode,
            "category": category_id,
            "sale_price": sale_price,
            "unit": unit
        }

        if Product.objects.filter(barcode=barcode).exists():
            product = Product.objects.get(barcode=barcode)
            product_serializer = ProductSerializer(product, data=product_data, partial=True)
        else:
            product_serializer = ProductSerializer(data=product_data)

        if not product_serializer.is_valid():
            return Response(product_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        product = product_serializer.save()

        # Создание новой партии (всегда новая партия, чтобы учесть другой срок годности)
        batch_data = {
            "product": product.id,
            "quantity": quantity,
            "expiration_date": expiration_date,
            "supplier": supplier,
            "purchase_price": request.data.get('purchase_price')
        }
        batch_serializer = ProductBatchSerializer(data=batch_data)
        if batch_serializer.is_valid():
            batch_serializer.save()
            return Response(
                {
                    "message": "Товар и партия успешно добавлены",
                    "product": ProductSerializer(product).data,
                    "batch": batch_serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        return Response(batch_serializer.errors, status=status.HTTP_400_BAD_REQUEST)