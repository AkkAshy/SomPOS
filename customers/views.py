from .models import Customer
from .serializers import CustomerSerializer
from rest_framework.views import APIView
from rest_framework import viewsets, status
from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from rest_framework import pagination
from django.db.models import Q

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    pagination_class = pagination.PageNumberPagination

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
                status=400
            )
        else:
            return super().create(request)
        # return super().create(request)

class CustomerSearchView(APIView):
    """
    Поиск клиентов по:
    - Полное имя (по частям)
    - Телефон (частичное совпадение)
    - Email
    """
    def get(self, request):
        query = request.query_params.get('q', '').strip()

        if not query:
            return Response({'results': []}, status=status.HTTP_200_OK)

        # Инициализация фильтра
        filters = Q()

        # Поиск по частям имени
        name_parts = query.split()
        for part in name_parts:
            filters |= Q(full_name__icontains=part)

        # Очищаем телефонный запрос
        phone_query = query.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')

        # Поиск по номеру телефона
        if phone_query.isdigit() or len(phone_query) >= 3:
            filters |= Q(phone__icontains=phone_query)

        # Поиск по email
        if '@' in query or (not phone_query.isdigit()):
            filters |= Q(email__icontains=query)

        # Выполняем запрос
        customers = Customer.objects.filter(filters).distinct()[:10]

        serializer = CustomerSerializer(customers, many=True)
        return Response({'results': serializer.data}, status=status.HTTP_200_OK)
