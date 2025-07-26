from django.contrib.auth.models import User, Group
from users.models import Employee

# Создаём пользователя
user = User.objects.create_user(
    username='admin',  # Имя администратора
    email='admin@example.com',
    password='admin123',  # Надёжный пароль
    first_name='Super',
    last_name='Admin',
    is_staff=True,  # Доступ к Django Admin
    is_superuser=True  # Полные права администратора
)

# Добавляем пользователя в группу 'admin'
try:
    admin_group = Group.objects.get(name='admin')
    user.groups.add(admin_group)
except Group.DoesNotExist:
    print("Группа 'admin' не найдена. Создайте её через setup_groups.py или вручную.")

# Создаём связанный объект Employee
Employee.objects.create(
    user=user,
    role='admin',
    phone='+998905755748',
    photo=None
)

# Проверяем, что пользователь создан
print(f"Пользователь создан: {user.username}, is_staff: {user.is_staff}, is_superuser: {user.is_superuser}")