from rest_framework import serializers
from .models import Customer, CustomerDebt
from django.utils.translation import gettext_lazy as _
from drf_yasg.utils import swagger_serializer_method
from drf_yasg import openapi
from django.core.validators import MinValueValidator


class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField(
        help_text="Полное имя клиента или 'Анонимный покупатель' если имя не указано"
    )
    
    class Meta:
        model = Customer
        fields = ['id', 'full_name', 'phone', 'debt', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'phone': {
                'help_text': "Номер телефона в международном формате",
                'required': True
            },
            'debt': {
                'help_text': "Сумма задолженности клиента",
                'validators': [MinValueValidator(0)],
            }
        }
        swagger_schema_fields = {
            'type': 'object',
            'properties': {
                'id': {
                    'type': 'integer',
                    'readOnly': True,
                    'example': 1
                },
                'full_name': {
                    'type': 'string',
                    'example': 'Иван Иванов'
                },
                'phone': {
                    'type': 'string',
                    'example': '+71234567890'
                },
                'total_spent':{
                    'type': 'number',
                    'format': 'positive-integer',
                    'example': 3
                },
                'created_at': {
                    'type': 'string',
                    'format': 'date-time',
                    'readOnly': True,
                    'example': '2023-05-15T14:30:00Z'
                }
            },
            'required': ['phone']
        }


    @swagger_serializer_method(serializer_or_field=serializers.CharField(help_text="Форматированное полное имя клиента"))
    def get_full_name(self, obj):
        return obj.full_name or _("Анонимный покупатель")

    def validate_phone(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Номер телефона не может быть пустым"))
        
        # Простая валидация формата номера
        if not value.startswith('+'):
            raise serializers.ValidationError(_("Номер должен начинаться с '+'"))
            
        if len(value) < 10:
            raise serializers.ValidationError(_("Слишком короткий номер телефона"))
            
        return value



class CustomerDebtSerializer(serializers.ModelSerializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        help_text="ID покупателя, которому принадлежит долг"
    )
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Сумма долга"
    )
    
    class Meta:
        model = CustomerDebt
        fields = ['id', 'customer', 'amount', 'created_at']
        read_only_fields = ['id', 'created_at']

        extra_kwargs = {
            'customer': {
                'help_text': "ID покупателя, которому принадлежит долг",
                'required': True
            },
            'amount': {
                'help_text': "Сумма долга",
                'validators': [MinValueValidator(0)],
                'required': True
            }
        }

