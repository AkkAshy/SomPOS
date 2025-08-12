from rest_framework import viewsets, pagination, status
from rest_framework.response import Response
from django.db.models import Q, Max
from django.utils.dateparse import parse_date
from drf_yasg.utils import swagger_auto_schema
from .serializers import CustomerSerializer
from .models import Customer

class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    pagination_class = pagination.PageNumberPagination

    def get_queryset(self):
        queryset = Customer.objects.annotate(
            annotated_last_purchase_date=Max(
                'purchases__created_at',
                filter=Q(purchases__status='completed')
            )
        )

        request = self.request
        query = request.query_params.get('q', '').strip()
        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')

        date_from = parse_date(date_from_str) if date_from_str else None
        date_to = parse_date(date_to_str) if date_to_str else None

        filters = Q()

        if query:
            name_parts = [word.capitalize() for word in query.split()]
            for part in name_parts:
                filters |= Q(full_name__icontains=part)

            phone_query = query.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
            if phone_query.isdigit() or len(phone_query) >= 3:
                filters |= Q(phone__icontains=phone_query)

            if '@' in query or not phone_query.isdigit():
                filters |= Q(email__icontains=query)

            queryset = queryset.filter(filters)

        if date_from:
            queryset = queryset.filter(annotated_last_purchase_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(annotated_last_purchase_date__date__lte=date_to)

        return queryset.distinct()

    @swagger_auto_schema(
        operation_description="Создание нового клиента",
        request_body=CustomerSerializer,
        responses={
            201: CustomerSerializer,
            400: "Невалидные данные"
        }
    )
    def create(self, request):
        number = request.data.get('number')

        if Customer.objects.filter(number=number).exists():
            return Response(
                {"message": "Клиент с таким номером уже существует."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request)
