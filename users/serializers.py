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
    employee = EmployeeSerializer(read_only=True)
    groups = serializers.SlugRelatedField(
        many=True,
        slug_field='name',
        queryset=Group.objects.all(),
        required=True
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'email', 'groups', 'first_name', 'last_name', 'employee']
        extra_kwargs = {
            'password': {'write_only': True}
        }

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

        instance.username = validated_data.get('username', instance.username)
        instance.email = validated_data.get('email', instance.email)
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        if 'password' in validated_data:
            instance.set_password(validated_data['password'])
        instance.save()

        if groups:
            instance.groups.set([Group.objects.get(name=name) for name in groups])

        if employee_data and hasattr(instance, 'employee'):
            employee = instance.employee
            employee.role = employee_data.get('role', employee.role)
            employee.phone = employee_data.get('phone', employee.phone)
            employee.photo = employee_data.get('photo', employee.photo)
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


