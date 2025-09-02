from rest_framework import viewsets, pagination, status
from rest_framework.response import Response
from django.db.models import Q, Max
from django.utils.dateparse import parse_date
from drf_yasg.utils import swagger_auto_schema
from .serializers import CustomerSerializer
from .models import Customer
from stores.mixins import StoreViewSetMixin

from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination



class FlexiblePagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 1000

    def paginate_queryset(self, queryset, request, view=None):
        self.request = request

        # 👉 если ни page, ни limit/offset нет — вернуть все данные
        if not request.query_params.get("page") and not request.query_params.get("limit") and not request.query_params.get("offset"):
            self.all_data = True
            self.queryset = list(queryset)
            return self.queryset

        # 👉 режим "все данные" по ?page=all
        if request.query_params.get("page") == "all":
            self.all_data = True
            self.queryset = list(queryset)
            return self.queryset

        # 👉 режим offset/limit
        limit = request.query_params.get("limit")
        offset = request.query_params.get("offset")
        if limit is not None:
            try:
                limit = int(limit)
                offset = int(offset or 0)
                self.all_data = False
                self.queryset = queryset[offset:offset + limit]
                self.count = queryset.count()
                return list(self.queryset)
            except ValueError:
                pass

        # 👉 fallback — обычная пагинация по страницам
        self.all_data = False
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        if getattr(self, "all_data", False):
            return Response({
                "count": len(data),
                "next": None,
                "previous": None,
                "results": data
            })

        if self.request.query_params.get("limit") is not None:
            next_offset = None
            offset = int(self.request.query_params.get("offset", 0))
            limit = int(self.request.query_params.get("limit", 0))
            if self.count > (offset + len(data)):
                next_offset = offset + len(data)
            prev_offset = offset - limit if offset > 0 else None
            if prev_offset is not None and prev_offset < 0:
                prev_offset = 0

            return Response({
                "count": self.count,
                "next": f"?limit={limit}&offset={next_offset}" if next_offset is not None else None,
                "previous": f"?limit={limit}&offset={prev_offset}" if prev_offset is not None else None,
                "results": data
            })

        return super().get_paginated_response(data)



class CustomerViewSet(StoreViewSetMixin, viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    pagination_class = FlexiblePagination

    def get_queryset(self):
        # Сначала получаем отфильтрованный по магазину queryset из миксина
        queryset = super().get_queryset()

        # Затем применяем дополнительные фильтры
        queryset = queryset.annotate(
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
