# analytics/views.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import SalesSummary, ProductAnalytics, CustomerAnalytics
from .serializers import SalesSummarySerializer, ProductAnalyticsSerializer, CustomerAnalyticsSerializer
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Count
from datetime import datetime, timedelta
from rest_framework.views import APIView
from decimal import Decimal

from sales.serializers import FilteredTransactionHistorySerializer
from sales.models import Transaction, TransactionHistory
from .funcs import get_date_range
from .pagination import OptionalPagination

from inventory.models import ProductBatch
import logging


logger = logging.getLogger(__name__)


class AnalyticsPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name__in=['admin', 'manager']).exists()

class SalesAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Простой ViewSet для аналитики продаж и закупок
    """
    queryset = SalesSummary.objects.all()
    serializer_class = SalesSummarySerializer
    permission_classes = [permissions.IsAuthenticated, AnalyticsPermission]
    pagination_class = OptionalPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['date', 'payment_method', 'cashier']
    ordering_fields = ['date', 'total_amount']
    ordering = ['-date']

    @swagger_auto_schema(
        operation_description="Получить финансовую сводку: продажи, закупки, прибыль за период",
        manual_parameters=[
            openapi.Parameter(
                'start_date',
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format='date',
                description="Дата начала периода (YYYY-MM-DD)"
            ),
            openapi.Parameter(
                'end_date',
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                format='date',
                description="Дата окончания периода (YYYY-MM-DD, по умолчанию сегодня)"
            ),
            openapi.Parameter(
                'cashier',
                openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="Фильтр по ID кассира"
            )
        ]
    )
    @action(detail=False, methods=['get'])
    def financial_summary(self, request):
        """
        Простая финансовая сводка: сколько потратили на закупки и сколько заработали
        """
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', timezone.now().date())
        cashier_id = request.query_params.get('cashier')

        # Парсинг дат
        if isinstance(end_date, str):
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                end_date = timezone.now().date()

        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                start_date = None

        # Валидация кассира
        if cashier_id:
            try:
                cashier_id = int(cashier_id)
            except ValueError:
                cashier_id = None

        # === ПРОДАЖИ ===
        sales_qs = self.get_queryset()

        if start_date:
            sales_qs = sales_qs.filter(date__gte=start_date)
        if end_date:
            sales_qs = sales_qs.filter(date__lte=end_date)
        if cashier_id:
            sales_qs = sales_qs.filter(cashier_id=cashier_id)

        # Группировка по методу оплаты
        payment_summary = list(
            sales_qs.values('payment_method')
            .annotate(
                total_amount=Sum('total_amount'),
                total_transactions=Sum('total_transactions'),
                total_items_sold=Sum('total_items_sold')
            )
            .order_by('payment_method')
        )

        # Общие суммы по продажам
        sales_totals = sales_qs.aggregate(
            total_amount=Sum('total_amount'),
            total_transactions=Sum('total_transactions'),
            total_items_sold=Sum('total_items_sold')
        )

        sales_revenue = sales_totals['total_amount'] or Decimal('0.00')

        # === ЗАКУПКИ ===
        purchase_qs = ProductBatch.objects.filter(
            purchase_price__isnull=False  # Только партии с указанной закупочной ценой
        )

        if start_date:
            purchase_qs = purchase_qs.filter(created_at__date__gte=start_date)
        if end_date:
            purchase_qs = purchase_qs.filter(created_at__date__lte=end_date)

        # Считаем общую сумму закупок
        purchase_totals = purchase_qs.aggregate(
            total_spent=Sum('purchase_price') * Sum('quantity') / Count('id'),  # Неточно, исправим
            total_batches=Count('id')
        )

        # Правильный расчет суммы закупок
        total_purchase_cost = Decimal('0.00')
        total_purchase_quantity = 0

        for batch in purchase_qs:
            if batch.purchase_price and batch.quantity:
                batch_cost = batch.purchase_price * batch.quantity
                total_purchase_cost += batch_cost
                total_purchase_quantity += batch.quantity

        # === РАСЧЕТ ПРИБЫЛИ ===
        # Простая прибыль = Выручка - Потрачено на закупки
        simple_profit = sales_revenue - total_purchase_cost

        # Рентабельность
        if sales_revenue > 0:
            profit_margin = (simple_profit / sales_revenue * 100)
        else:
            profit_margin = Decimal('0.00')

        response_data = {
            # Продажи
            'sales': {
                'total_revenue': sales_revenue,
                'total_transactions': sales_totals['total_transactions'] or 0,
                'total_items_sold': sales_totals['total_items_sold'] or 0,
                'payment_summary': payment_summary,
            },

            # Закупки
            'purchases': {
                'total_spent': total_purchase_cost,
                'total_quantity': total_purchase_quantity,
                'total_batches': purchase_qs.count(),
                'average_unit_cost': (total_purchase_cost / total_purchase_quantity) if total_purchase_quantity > 0 else Decimal('0.00')
            },

            # Итог
            'summary': {
                'revenue': sales_revenue,
                'costs': total_purchase_cost,
                'profit': simple_profit,
                'profit_margin': round(profit_margin, 2)
            },

            # Период
            'period': {
                'start_date': start_date,
                'end_date': end_date,
                'cashier_id': cashier_id
            }
        }

        logger.info(f"Simple financial summary: revenue={sales_revenue}, costs={total_purchase_cost}, profit={simple_profit}")
        return Response(response_data)

    @swagger_auto_schema(
        operation_description="Детализация закупок за период",
        manual_parameters=[
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('product_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description="Фильтр по товару")
        ]
    )
    @action(detail=False, methods=['get'])
    def purchases_detail(self, request):
        """
        Детализация по закупкам
        """
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', timezone.now().date())
        product_id = request.query_params.get('product_id')

        # Парсинг дат
        if isinstance(end_date, str):
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                end_date = timezone.now().date()

        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                start_date = None

        # Базовый queryset
        batches_qs = ProductBatch.objects.select_related('product').filter(
            purchase_price__isnull=False
        )

        # Фильтры
        if start_date:
            batches_qs = batches_qs.filter(created_at__date__gte=start_date)
        if end_date:
            batches_qs = batches_qs.filter(created_at__date__lte=end_date)
        if product_id:
            try:
                batches_qs = batches_qs.filter(product_id=int(product_id))
            except ValueError:
                pass

        # Собираем данные по закупкам
        purchases_data = []
        total_cost = Decimal('0.00')
        total_quantity = 0

        for batch in batches_qs.order_by('-created_at'):
            batch_total = batch.purchase_price * batch.quantity
            total_cost += batch_total
            total_quantity += batch.quantity

            purchases_data.append({
                'id': batch.id,
                'product_id': batch.product.id,
                'product_name': batch.product.name,
                'quantity': batch.quantity,
                'unit_price': batch.purchase_price,
                'total_cost': batch_total,
                'supplier': batch.supplier,
                'date': batch.created_at.date(),
                'expiration_date': batch.expiration_date,
            })

        return Response({
            'purchases': purchases_data,
            'summary': {
                'total_batches': len(purchases_data),
                'total_quantity': total_quantity,
                'total_cost': total_cost,
                'average_unit_cost': (total_cost / total_quantity) if total_quantity > 0 else Decimal('0.00')
            },
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'product_id': product_id
            }
        })

    @swagger_auto_schema(
        operation_description="Оригинальная сводка по продажам",
        manual_parameters=[
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('cashier', openapi.IN_QUERY, type=openapi.TYPE_INTEGER)
        ]
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Оригинальный метод summary (для обратной совместимости)
        """
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', timezone.now().date())
        cashier_id = request.query_params.get('cashier')

        queryset = self.get_queryset()

        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        if cashier_id:
            try:
                cashier_id = int(cashier_id)
                queryset = queryset.filter(cashier_id=cashier_id)
            except ValueError:
                pass

        # Группировка по методу оплаты
        payment_summary = list(
            queryset.values('payment_method')
            .annotate(
                total_amount=Sum('total_amount'),
                total_transactions=Sum('total_transactions'),
                total_items_sold=Sum('total_items_sold')
            )
            .order_by('payment_method')
        )

        # Общие суммы
        totals = queryset.aggregate(
            total_amount=Sum('total_amount'),
            total_transactions=Sum('total_transactions'),
            total_items_sold=Sum('total_items_sold')
        )

        return Response({
            'payment_summary': payment_summary,
            'total_amount': totals['total_amount'] or 0,
            'total_transactions': totals['total_transactions'] or 0,
            'total_items_sold': totals['total_items_sold'] or 0
        })

class ProductAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для аналитики товаров.
    """
    queryset = ProductAnalytics.objects.select_related('product').all()
    serializer_class = ProductAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated, AnalyticsPermission]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['product', 'date']
    ordering_fields = ['date', 'quantity_sold', 'revenue']
    ordering = ['-date']

    @swagger_auto_schema(
        operation_description="Получить топ продаваемых товаров",
        manual_parameters=[
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=10),
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date')
        ]
    )
    @action(detail=False, methods=['get'])
    def top_products(self, request):
        limit = int(request.query_params.get('limit', 10))
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', datetime.today().date())

        queryset = self.get_queryset()
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        top_products = queryset.values('product__name').annotate(
            total_quantity=Sum('quantity_sold'),
            total_revenue=Sum('revenue')
        ).order_by('-total_quantity')[:limit]

        return Response({
            'top_products': top_products,
            'limit': limit
        })

class CustomerAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для аналитики клиентов.
    """
    queryset = CustomerAnalytics.objects.select_related('customer').all()
    serializer_class = CustomerAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated, AnalyticsPermission]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['customer', 'date']
    ordering_fields = ['date', 'total_purchases', 'transaction_count', 'debt_added']
    ordering = ['-date']

    @swagger_auto_schema(
        operation_description="Получить топ клиентов по покупкам",
        manual_parameters=[
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=10),
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date')
        ]
    )
    @action(detail=False, methods=['get'])
    def top_customers(self, request):
        limit = int(request.query_params.get('limit', 10))
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', datetime.today().date())

        queryset = self.get_queryset()
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        top_customers = queryset.values('customer__full_name', 'customer__phone').annotate(
            total_purchases=Sum('total_purchases'),
            total_transactions=Sum('transaction_count'),
            total_debt=Sum('debt_added')
        ).order_by('-total_purchases')[:limit]

        return Response({
            'top_customers': top_customers,
            'limit': limit
        })


class TransactionsHistoryByDayView(APIView):
    def get(self, request):
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")

        if not date_from or not date_to:
            return Response({"error": "Uncorrect datas"})

        try:
            dates = get_date_range(date_from, date_to)
            trasnactions_list = []
            for date in dates:
                trasnactions = TransactionHistory.objects.filter(created_at__date=date).all()
                trasnactions = FilteredTransactionHistorySerializer(trasnactions, many=True).data
                if trasnactions:
                    amounts = 0
                    for transaction in trasnactions:
                        try:
                            amount = float(transaction["parsed_details"]["total_amount"])
                        except:
                            amount = 0
                        amounts += amount
                    trasnactions_list.append({date: amounts})

            return Response(trasnactions_list)
        except Exception as e:
            return Response({"error": str(e)})
