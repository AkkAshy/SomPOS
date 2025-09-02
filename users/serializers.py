# auth/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User, Group
from .models import Employee
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from stores.models import StoreEmployee
from stores.tokens import get_tokens_for_user_and_store

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ['role', 'phone', 'photo']
        extra_kwargs = {
            'photo': {'required': False, 'allow_null': True}
        }

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    employee = EmployeeSerializer(required=False)  # ✅ изменено
    groups = serializers.SlugRelatedField(
        many=True,
        slug_field='name',
        queryset=Group.objects.all(),
        required=True
    )
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'groups', 'first_name', 'last_name',
            'full_name', 'employee', 'password',
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

    def get_employee(self, obj):
        try:
            employee = obj.employee  # Получаем связанного сотрудника
            return EmployeeSerializer(employee).data
        except Employee.DoesNotExist:
            return None

    def create(self, validated_data):
        employee_data = validated_data.pop('employee', None)
        groups = validated_data.pop('groups')
        password = validated_data.pop('password')

        user = User.objects.create_user(password=password, **validated_data)
        user.groups.set([Group.objects.get(name=name) for name in groups])

        if employee_data:
            Employee.objects.create(user=user, **employee_data)

        return user

    def update(self, instance, validated_data):
        employee_data = validated_data.pop('employee', None)
        groups = validated_data.pop('groups', None)
        password = validated_data.pop('password', None)

        # обновляем пользователя
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()

        # обновляем группы, если переданы
        if groups is not None:
            instance.groups.set([Group.objects.get(name=name) for name in groups])

        # обновляем employee
        if employee_data:
            employee, _ = Employee.objects.get_or_create(user=instance)
            for attr, value in employee_data.items():
                setattr(employee, attr, value)
            employee.save()

        return instance


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    store_id = serializers.UUIDField(required=False, help_text="ID магазина (опционально)")

    def validate(self, data):
        username = data.get('username')
        password = data.get('password')
        store_id = data.get('store_id')

        user = authenticate(
            request=self.context.get('request'),
            username=username,
            password=password
        )

        if user and user.is_active:
            # Получаем магазины пользователя
            store_memberships = StoreEmployee.objects.filter(
                user=user,
                is_active=True
            ).select_related('store')

            # Если у пользователя нет магазинов
            if not store_memberships.exists():
                raise serializers.ValidationError(
                    _("Пользователь не привязан ни к одному магазину. Обратитесь к администратору.")
                )

            # Если магазин не указан, берем первый доступный
            if not store_id:
                first_membership = store_memberships.first()
                if first_membership:
                    store_id = str(first_membership.store.id)
            else:
                # Проверяем доступ к указанному магазину
                if not store_memberships.filter(store_id=store_id).exists():
                    raise serializers.ValidationError(
                        _("У вас нет доступа к указанному магазину")
                    )

            # Генерируем токены с информацией о магазине
            tokens = get_tokens_for_user_and_store(user, store_id)

            # Получаем информацию о текущем магазине
            current_membership = store_memberships.filter(store_id=store_id).first()

            # Список всех доступных магазинов
            stores_data = []
            for membership in store_memberships:
                stores_data.append({
                    'id': str(membership.store.id),
                    'name': membership.store.name,
                    'role': membership.role,
                    'logo': membership.store.logo.url if membership.store.logo else None,
                    'is_current': str(membership.store.id) == store_id
                })

            return {
                'username': user.username,
                'access': tokens['access'],
                'refresh': tokens['refresh'],
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'full_name': user.get_full_name()
                },
                'current_store': {
                    'id': tokens['store_id'],
                    'name': tokens['store_name'],
                    'role': tokens['store_role']
                } if current_membership else None,
                'available_stores': stores_data,
                'role': user.employee.role if hasattr(user, 'employee') else None
            }

        raise serializers.ValidationError(_("Неверные учетные данные"))


