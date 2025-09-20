from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import SalesSummary, ProductAnalytics, CustomerAnalytics, SupplierAnalytics, CashRegister
from .serializers import SalesSummarySerializer, ProductAnalyticsSerializer, CustomerAnalyticsSerializer, SupplierAnalyticsSerializer, CashRegisterSerializer, CashHistorySerializer, CashRegisterCloseSerializer
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Count, F, Avg, Q
from datetime import datetime, timedelta
from rest_framework.views import APIView
from decimal import Decimal
from rest_framework.exceptions import PermissionDenied


from sales.serializers import FilteredTransactionHistorySerializer
from sales.models import Transaction, TransactionHistory
from .funcs import get_date_range
from .pagination import OptionalPagination

from inventory.models import ProductBatch
from stores.mixins import StoreViewSetMixin  # ← ДОБАВЛЯЕМ МИКСИН
import logging

logger = logging.getLogger(__name__)


class AnalyticsPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name__in=['admin', 'manager', 'owner']).exists()


class CashRegisterViewSet(StoreViewSetMixin, viewsets.ModelViewSet):
    """
    ✅ VIEWSET КАССЫ — просмотр баланса и снятие
    """
    queryset = CashRegister.objects.filter(is_open=True)  # Только открытые смены
    serializer_class = CashRegisterSerializer
    permission_classes = [AnalyticsPermission]
    
    def get_queryset(self):
        store = self.get_current_store()
        return super().get_queryset().filter(store=store)

    def retrieve(self, request, *args, **kwargs):
        """GET: текущий баланс кассы"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            'current_balance': serializer.data['current_balance'],
            'formatted': serializer.data['balance_formatted'],
            'is_open': instance.is_open,
            'message': f"На кассе {serializer.data['balance_formatted']}. Смена открыта."
        })

    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        """POST: кнопка 'забери' — снимаем сумму"""
        instance = self.get_object()
        amount = request.data.get('amount')
        notes = request.data.get('notes', 'Выдача наличных')
        
        if not amount:
            return Response({'error': 'Укажите сумму'}, status=400)
        
        try:
            withdrawn = instance.withdraw(amount, request.user, notes)
            return Response({
                'success': True,
                'withdrawn': float(withdrawn),
                'new_balance': float(instance.current_balance),
                'message': f"Снято {withdrawn:,.0f} сум. Остаток: {instance.current_balance:,.0f} сум."
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['post'])
    def open_shift(self, request):
        """POST: открыть новую смену (если нужно)"""
        store = self.get_current_store()
        # Создаём, если нет открытой
        if CashRegister.objects.filter(store=store, is_open=True).exists():
            return Response({'error': 'Смена уже открыта'}, status=400)
        
        target = request.data.get('target_balance', Decimal('0.00'))
        instance = CashRegister.objects.create(store=store, target_balance=target)
        return Response({'id': instance.id, 'message': 'Смена открыта. Баланс: 0 сум'})
    
    @action(detail=True, methods=['post'])
    def close_shift(self, request, pk=None):
        """POST: закрыть смену — ритуал конца дня"""
        instance = self.get_object()
        
        if not instance.is_open:
            return Response({'error': 'Смена уже закрыта'}, status=400)
        
        serializer = CashRegisterCloseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        
        actual_balance = serializer.validated_data['actual_balance']
        notes = serializer.validated_data['notes']
        
        try:
            result = instance.close_shift(actual_balance, request.user, notes)
            
            # Возвращаем обновлённые данные
            updated_serializer = self.get_serializer(instance)
            return Response({
                'success': True,
                'status': result['status'],
                'discrepancy': float(result['discrepancy']),
                'message': result['message'],
                'final_balance': float(instance.closed_balance),
                'closed_at': instance.closed_at.isoformat() if instance.closed_at else None,
                'cash_register': updated_serializer.data
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """GET: история операций по кассе"""
        instance = self.get_object()
        history = instance.history.select_related('user').order_by('-timestamp')[:50]  # Последние 50
        serializer = CashHistorySerializer(history, many=True)
        return Response({
            'cash_register': instance.id,
            'total_operations': history.count(),
            'history': serializer.data
        })

class SupplierAnalyticsViewSet(StoreViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для аналитики поставщиков — чей товар улетает, а чей пылится.
    """
    queryset = SupplierAnalytics.objects.all()  # Если persistent; иначе переопредели get_queryset для агрегации
    serializer_class = SupplierAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated, AnalyticsPermission]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['supplier', 'date']
    ordering_fields = ['date', 'total_revenue', 'total_margin']
    ordering = ['-date']

    def get_queryset(self):
        current_store = self.get_current_store()
        if not current_store:
            raise PermissionDenied("Магазин не определен")
        return super().get_queryset().filter(store=current_store)

    @swagger_auto_schema(
        operation_description="Получить топ поставщиков по выручке/марже",
        manual_parameters=[
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=10),
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('metric', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=['revenue', 'margin', 'turnover'], default='revenue')
        ]
    )
    @action(detail=False, methods=['get'])
    def top_suppliers(self, request):
        current_store = self.get_current_store()
        if not current_store:
            return Response({'error': 'Магазин не определен'}, status=400)

        limit = int(request.query_params.get('limit', 10))
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', timezone.now().date())
        metric = request.query_params.get('metric', 'revenue')  # Сортировка по revenue/margin/turnover

        # Если модель не persistent, агрегируем из StockHistory
        from inventory.models import StockHistory  # Импорт здесь, чтобы избежать цикла
        sales_qs = StockHistory.objects.filter(
            store=current_store,
            operation_type='SALE',
            batch__isnull=False
        )
        if start_date:
            sales_qs = sales_qs.filter(date_only__gte=start_date)
        if end_date:
            sales_qs = sales_qs.filter(date_only__lte=end_date)

        supplier_data = sales_qs.values('batch__supplier').annotate(
            total_sold=Sum(F('quantity_change') * -1),
            total_revenue=Sum(F('quantity_change') * -1 * F('sale_price_at_time')),
            total_cost=Sum(F('quantity_change') * -1 * F('purchase_price_at_time')),
            total_margin=Sum(
                (F('quantity_change') * -1 * F('sale_price_at_time')) -
                (F('quantity_change') * -1 * F('purchase_price_at_time'))
            ),
            unique_products=Count('product', distinct=True),
            transactions_count=Count('id'),
            avg_margin_pct=Avg(
                ((F('sale_price_at_time') - F('purchase_price_at_time')) / F('sale_price_at_time')) * 100,
                filter=Q(sale_price_at_time__gt=0)
            ),
            turnover_rate=Sum(F('quantity_change') * -1) / Avg('product__stock__quantity')  # Адаптируй
        ).order_by(f'-total_{metric}')[:limit]  # Динамическая сортировка

        # Инсайты
        insights = self._get_supplier_insights(supplier_data)

        return Response({
            'store': {'id': str(current_store.id), 'name': current_store.name},
            'top_suppliers': list(supplier_data),
            'insights': insights,
            'period': {'start_date': start_date, 'end_date': end_date},
            'metric': metric,
            'limit': limit
        })

    def _get_supplier_insights(self, data):
        # Аналогично моему предыдущему совету: генерируем рекомендации
        if not data:
            return [{'type': 'no_data', 'title': 'Нет данных', 'description': 'Проверьте продажи и партии.'}]
        
        insights = []
        top = data[0]
        insights.append({
            'type': 'top_supplier',
            'title': f'Лучший: {top["batch__supplier"]}',
            'description': f'Выручка {top["total_revenue"]:,}, маржа {top["total_margin"]:,}.',
            'action': 'Увеличьте объёмы.'
        })
        
        low_margin = [s for s in data if s['avg_margin_pct'] < 20]
        if low_margin:
            insights.append({
                'type': 'low_margin',
                'title': 'Проблемные по марже',
                'description': f'{len(low_margin)} с маржей <20%.',
                'action': 'Переговоры или замена.'
            })
        
        return insights

class SalesAnalyticsViewSet(StoreViewSetMixin, viewsets.ReadOnlyModelViewSet):  # ← ДОБАВЛЯЕМ МИКСИН
    """
    Простой ViewSet для аналитики продаж и закупок
    """
    queryset = SalesSummary.objects.all()  # ← ДОБАВЛЯЕМ БАЗОВЫЙ QUERYSET
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
        # ✅ ПОЛУЧАЕМ ТЕКУЩИЙ МАГАЗИН
        current_store = self.get_current_store()
        if not current_store:
            return Response({
                'error': 'Магазин не определен. Переавторизуйтесь или выберите магазин.',
                'debug_info': {
                    'user': request.user.username,
                    'has_current_store': hasattr(request.user, 'current_store'),
                    'current_store_value': getattr(request.user, 'current_store', None)
                }
            }, status=400)

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

        # === ПРОДАЖИ (ТОЛЬКО ТЕКУЩИЙ МАГАЗИН) ===
        sales_qs = SalesSummary.objects.filter(store=current_store)  # ← ФИЛЬТР ПО МАГАЗИНУ

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

        # === ЗАКУПКИ (ТОЛЬКО ТЕКУЩИЙ МАГАЗИН) ===
        purchase_qs = ProductBatch.objects.filter(
            store=current_store,  # ← ФИЛЬТР ПО МАГАЗИНУ
            purchase_price__isnull=False
        )

        if start_date:
            purchase_qs = purchase_qs.filter(created_at__date__gte=start_date)
        if end_date:
            purchase_qs = purchase_qs.filter(created_at__date__lte=end_date)

        # Правильный расчет суммы закупок
        total_purchase_cost = Decimal('0.00')
        total_purchase_quantity = 0

        for batch in purchase_qs:
            if batch.purchase_price and batch.quantity:
                batch_cost = batch.purchase_price * batch.quantity
                total_purchase_cost += batch_cost
                total_purchase_quantity += batch.quantity

        # === РАСЧЕТ ПРИБЫЛИ ===
        simple_profit = sales_revenue - total_purchase_cost

        # Рентабельность
        if sales_revenue > 0:
            profit_margin = (simple_profit / sales_revenue * 100)
        else:
            profit_margin = Decimal('0.00')

        response_data = {
            # Информация о магазине
            'store': {
                'id': str(current_store.id),
                'name': current_store.name
            },

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

        logger.info(f"Financial summary for store {current_store.name}: revenue={sales_revenue}, costs={total_purchase_cost}, profit={simple_profit}")
        return Response(response_data)

    @action(detail=False, methods=['get'])
    def purchases_detail(self, request):
        """
        Детализация по закупкам (только текущий магазин)
        """
        # ✅ ПОЛУЧАЕМ ТЕКУЩИЙ МАГАЗИН
        current_store = self.get_current_store()
        if not current_store:
            return Response({'error': 'Магазин не определен'}, status=400)

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

        # Базовый queryset С ФИЛЬТРОМ ПО МАГАЗИНУ
        batches_qs = ProductBatch.objects.select_related('product').filter(
            store=current_store,  # ← ФИЛЬТР ПО МАГАЗИНУ
            purchase_price__isnull=False
        )

        # Остальные фильтры
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
            'store': {
                'id': str(current_store.id),
                'name': current_store.name
            },
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

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Оригинальный метод summary (для обратной совместимости)
        """
        # ✅ ПОЛУЧАЕМ ТЕКУЩИЙ МАГАЗИН
        current_store = self.get_current_store()
        if not current_store:
            return Response({'error': 'Магазин не определен'}, status=400)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', timezone.now().date())
        cashier_id = request.query_params.get('cashier')

        # ФИЛЬТРУЕМ ПО МАГАЗИНУ
        queryset = SalesSummary.objects.filter(store=current_store)

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
            'store': {
                'id': str(current_store.id),
                'name': current_store.name
            },
            'payment_summary': payment_summary,
            'total_amount': totals['total_amount'] or 0,
            'total_transactions': totals['total_transactions'] or 0,
            'total_items_sold': totals['total_items_sold'] or 0
        })


class ProductAnalyticsViewSet(StoreViewSetMixin, viewsets.ReadOnlyModelViewSet):  # ← ДОБАВЛЯЕМ МИКСИН
    """
    ViewSet для аналитики товаров.
    """
    queryset = ProductAnalytics.objects.select_related('product').all()  # ← ДОБАВЛЯЕМ БАЗОВЫЙ QUERYSET
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
        # ✅ ПОЛУЧАЕМ ТЕКУЩИЙ МАГАЗИН
        current_store = self.get_current_store()
        if not current_store:
            return Response({'error': 'Магазин не определен'}, status=400)

        limit = int(request.query_params.get('limit', 10))
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', datetime.today().date())

        # ФИЛЬТРУЕМ ПО ТОВАРАМ ТЕКУЩЕГО МАГАЗИНА
        queryset = ProductAnalytics.objects.filter(
            product__store=current_store  # ← ФИЛЬТР ПО МАГАЗИНУ
        )

        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        top_products = queryset.values('product__name').annotate(
            total_quantity=Sum('quantity_sold'),
            total_revenue=Sum('revenue')
        ).order_by('-total_quantity')[:limit]

        return Response({
            'store': {
                'id': str(current_store.id),
                'name': current_store.name
            },
            'top_products': top_products,
            'limit': limit
        })


class CustomerAnalyticsViewSet(StoreViewSetMixin, viewsets.ReadOnlyModelViewSet):  # ← ДОБАВЛЯЕМ МИКСИН
    """
    ViewSet для аналитики клиентов.
    """
    queryset = CustomerAnalytics.objects.select_related('customer').all()  # ← ДОБАВЛЯЕМ БАЗОВЫЙ QUERYSET
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
        # ✅ ПОЛУЧАЕМ ТЕКУЩИЙ МАГАЗИН
        current_store = self.get_current_store()
        if not current_store:
            return Response({'error': 'Магазин не определен'}, status=400)

        limit = int(request.query_params.get('limit', 10))
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', datetime.today().date())

        # ФИЛЬТРУЕМ ПО КЛИЕНТАМ ТЕКУЩЕГО МАГАЗИНА
        queryset = CustomerAnalytics.objects.filter(
            customer__store=current_store  # ← ФИЛЬТР ПО МАГАЗИНУ
        )

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
            'store': {
                'id': str(current_store.id),
                'name': current_store.name
            },
            'top_customers': top_customers,
            'limit': limit
        })


class TransactionsHistoryByDayView(StoreViewSetMixin, APIView):  # ← ДОБАВЛЯЕМ МИКСИН
    def get(self, request):
        # ✅ ПОЛУЧАЕМ ТЕКУЩИЙ МАГАЗИН
        current_store = self.get_current_store()
        if not current_store:
            return Response({"error": "Магазин не определен"}, status=400)

        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")

        if not date_from or not date_to:
            return Response({"error": "Uncorrect datas"})

        try:
            dates = get_date_range(date_from, date_to)
            transactions_list = []

            for date in dates:
                # ФИЛЬТРУЕМ ПО МАГАЗИНУ
                transactions = TransactionHistory.objects.filter(
                    store=current_store,  # ← ФИЛЬТР ПО МАГАЗИНУ
                    created_at__date=date
                ).all()

                transactions = FilteredTransactionHistorySerializer(transactions, many=True).data

                if transactions:
                    amounts = 0
                    for transaction in transactions:
                        try:
                            amount = float(transaction["parsed_details"]["total_amount"])
                        except:
                            amount = 0
                        amounts += amount
                    transactions_list.append({date: amounts})

            return Response({
                'store': {
                    'id': str(current_store.id),
                    'name': current_store.name
                },
                'transactions_by_day': transactions_list
            })
        except Exception as e:
            return Response({"error": str(e)})