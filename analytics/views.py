# analytics/views.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import SalesSummary, ProductAnalytics, CustomerAnalytics
from .serializers import SalesSummarySerializer, ProductAnalyticsSerializer, CustomerAnalyticsSerializer
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum
from datetime import datetime, timedelta
from rest_framework.views import APIView
from django.db.models import Sum
from datetime import datetime

from sales.serializers import FilteredTransactionHistorySerializer
from sales.models import Transaction, TransactionHistory
from .funcs import get_date_range


class AnalyticsPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name__in=['admin', 'manager']).exists()

class SalesAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet для аналитики продаж.
    """
    queryset = SalesSummary.objects.all()
    serializer_class = SalesSummarySerializer
    permission_classes = [permissions.IsAuthenticated, AnalyticsPermission]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['date', 'payment_method']
    ordering_fields = ['date', 'total_amount']
    ordering = ['-date']

    @swagger_auto_schema(
        operation_description="Получить сводку по продажам за период",
        manual_parameters=[
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date'),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING, format='date')
        ]
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', datetime.today().date())

        queryset = self.get_queryset()
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        # Группировка по методу оплаты
        payment_summary = (
            queryset.values('payment_method')
            .annotate(
                total_amount=Sum('total_amount'),
                total_transactions=Sum('total_transactions'),
                total_items_sold=Sum('total_items_sold')
            )
            .order_by('payment_method')
        )

        # Общие суммы
        total_amount = queryset.aggregate(total=Sum('total_amount'))['total'] or 0
        total_transactions = queryset.aggregate(total=Sum('total_transactions'))['total'] or 0
        total_items_sold = queryset.aggregate(total=Sum('total_items_sold'))['total'] or 0

        return Response({
            'payment_summary': payment_summary,  # сгруппировано по методу оплаты
            'total_amount': total_amount,
            'total_transactions': total_transactions,
            'total_items_sold': total_items_sold
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
