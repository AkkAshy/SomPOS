# auth/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User, Group
from .models import Employee
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

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

    def validate(self, data):
        username = data.get('username')
        password = data.get('password')

        print(f'Валидация: {username=} {password=}')
        user = authenticate(request=self.context.get('request'), username=username, password=password)
        print(f'Найден пользователь: {user}')

        if user and user.is_active:
            refresh = RefreshToken.for_user(user)
            return {
                'username': user.username,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'role': user.employee.role if hasattr(user, 'employee') else None
            }
        raise serializers.ValidationError(_("Неверные учетные данные"))


