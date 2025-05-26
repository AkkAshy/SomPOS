# inventory/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from .models import Product, ProductCategory, Stock, ProductBatch
from .serializers import ProductSerializer, ProductCategorySerializer, StockSerializer, ProductBatchSerializer, SaleSerializer

logger = logging.getLogger('inventory')

class ProductCategoryCreateView(APIView):
    def post(self, request):
        logger.debug(f"[SomPOS] Creating category: {request.data}")
        serializer = ProductCategorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            logger.info(f"[SomPOS] Created category: {serializer.data['name']}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning(f"[SomPOS] Invalid category data: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProductCategoryListView(APIView):
    def get(self, request):
        logger.debug("[SomPOS] Fetching category list")
        categories = ProductCategory.objects.all()
        serializer = ProductCategorySerializer(categories, many=True)
        logger.info(f"[SomPOS] Retrieved {len(categories)} categories")
        return Response(serializer.data)

class ProductCreateView(APIView):
    def post(self, request):
        logger.debug(f"[SomPOS] Creating product: {request.data}")
        serializer = ProductSerializer(data=request.data)
        if serializer.is_valid():
            product = serializer.save()
            logger.info(f"[SomPOS] Created product: {product.name} with barcode: {product.barcode}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning(f"[SomPOS] Invalid product data: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProductListView(APIView):
    def get(self, request):
        logger.debug("[SomPOS] Fetching product list")
        products = Product.objects.all()
        serializer = ProductSerializer(products, many=True)
        logger.info(f"[SomPOS] Retrieved {len(products)} products")
        return Response(serializer.data)

class ProductSearchView(APIView):
    def get(self, request):
        query = request.query_params.get('q', '')
        logger.debug(f"[SomPOS] Searching products with query: {query}")
        products = Product.objects.filter(Q(name__icontains=query))
        serializer = ProductSerializer(products, many=True)
        logger.info(f"[SomPOS] Found {len(products)} products for query: {query}")
        return Response(serializer.data)

class ProductSearchByBarcodeView(APIView):
    def get(self, request):
        barcode = request.query_params.get('barcode', '')
        logger.debug(f"[SomPOS] Searching product with barcode: {barcode}")
        if not barcode:
            logger.warning("[SomPOS] Barcode is missing")
            return Response({"error": "Barcode is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            product = Product.objects.filter(barcode=barcode).first()
            if product:
                logger.info(f"[SomPOS] Found product: {product.name} with barcode: {barcode}")
                return Response({
                    'product': ProductSerializer(product).data,
                    'message': 'Product found'
                }, status=status.HTTP_200_OK)
            logger.info(f"[SomPOS] No product found with barcode: {barcode}")
            return Response({
                'message': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"[SomPOS] Error searching barcode: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StockUpdateView(APIView):
    def post(self, request):
        logger.debug(f"[SomPOS] Updating stock: {request.data}")
        product_id = request.data.get('product_id')
        quantity_change = request.data.get('quantity_change')
        try:
            stock = Stock.objects.get(product_id=product_id)
            stock.quantity += int(quantity_change)
            stock.save()
            logger.info(f"[SomPOS] Updated stock for product {stock.product.name}: {stock.quantity}")
            serializer = StockSerializer(stock)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Stock.DoesNotExist:
            logger.error(f"[SomPOS] Stock not found for product_id: {product_id}")
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError:
            logger.error(f"[SomPOS] Invalid quantity_change: {quantity_change}")
            return Response({"error": "Quantity must be a number"}, status=status.HTTP_400_BAD_REQUEST)

class ProductBatchCreateView(APIView):
    def post(self, request):
        logger.debug(f"[SomPOS] Creating batch: {request.data}")
        serializer = ProductBatchSerializer(data=request.data)
        if serializer.is_valid():
            batch = serializer.save()
            logger.info(f"[SomPOS] Created batch for {batch.product.name}: {batch.quantity}, expires: {batch.expiration_date}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning(f"[SomPOS] Invalid batch data: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProductScanCheckView(APIView):
    def post(self, request):
        logger.debug(f"[SomPOS] Checking barcode: {request.data}")
        barcode = request.data.get('barcode')
        
        if not barcode:
            logger.warning("[SomPOS] Barcode is missing")
            return Response({"error": "Barcode is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.filter(barcode=barcode).first()
            if product:
                logger.info(f"[SomPOS] Found product: {product.name} with barcode: {barcode}")
                return Response({
                    'product': ProductSerializer(product).data,
                    'message': 'Product found'
                }, status=status.HTTP_200_OK)
            logger.info(f"[SomPOS] No product found with barcode: {barcode}")
            return Response({
                'message': 'Product not found, please create a new one'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"[SomPOS] Error checking barcode: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProductScanCreateView(APIView):
    def post(self, request):
        logger.debug(f"[SomPOS] Creating product from scan: {request.data}")
        barcode = request.data.get('barcode')
        quantity = request.data.get('quantity', 1)
        expiration_date = request.data.get('expiration_date')
        
        if not barcode:
            logger.warning("[SomPOS] Barcode is missing")
            return Response({"error": "Barcode is required"}, status=status.HTTP_400_BAD_REQUEST)

        product_data = {
            'barcode': barcode,
            'name': request.data.get('name'),
            'category': request.data.get('category'),
            'unit': request.data.get('unit', 'piece'),
            'sale_price': request.data.get('sale_price')
        }
        
        try:
            if Product.objects.filter(barcode=barcode).exists():
                logger.warning(f"[SomPOS] Barcode already exists: {barcode}")
                return Response({"error": "Barcode already exists"}, status=status.HTTP_400_BAD_REQUEST)
            
            if not all([product_data['name'], product_data['category'], product_data['sale_price']]):
                logger.warning(f"[SomPOS] Missing required fields: {product_data}")
                return Response({"error": "Name, category, and sale_price are required"}, status=status.HTTP_400_BAD_REQUEST)
            
            product_serializer = ProductSerializer(data=product_data)
            if product_serializer.is_valid():
                product = product_serializer.save()
                batch_data = {
                    'product': product.id,
                    'quantity': quantity,
                    'expiration_date': expiration_date
                }
                batch_serializer = ProductBatchSerializer(data=batch_data)
                if batch_serializer.is_valid():
                    batch = batch_serializer.save()
                    logger.info(f"[SomPOS] Created product: {product.name} with barcode: {barcode}, batch: {batch.quantity}")
                    return Response({
                        'product': product_serializer.data,
                        'batch': batch_serializer.data,
                        'message': 'New product and batch created'
                    }, status=status.HTTP_201_CREATED)
                logger.warning(f"[SomPOS] Invalid batch data: {batch_serializer.errors}")
                return Response(batch_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            logger.warning(f"[SomPOS] Invalid product data: {product_serializer.errors}")
            return Response(product_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[SomPOS] Error creating product: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SaleCreateView(APIView):
    def post(self, request):
        logger.debug(f"[SomPOS] Creating sale: {request.data}")
        serializer = SaleSerializer(data=request.data)
        if serializer.is_valid():
            product_id = serializer.validated_data['product_id']
            quantity = serializer.validated_data['quantity']
            try:
                stock = Stock.objects.get(product_id=product_id)
                stock.sell(quantity)
                logger.info(f"[SomPOS] Sale created for product {stock.product.name}: {quantity} units")
                return Response({
                    'product': ProductSerializer(stock.product).data,
                    'quantity_sold': quantity,
                    'remaining_stock': stock.quantity
                }, status=status.HTTP_200_OK)
            except Stock.DoesNotExist:
                logger.error(f"[SomPOS] Stock not found for product_id: {product_id}")
                return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
            except ValueError as e:
                logger.error(f"[SomPOS] Sale error: {e}")
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        logger.warning(f"[SomPOS] Invalid sale data: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)