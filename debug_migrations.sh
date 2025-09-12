#!/bin/bash

echo "=== ДИАГНОСТИКА ПРОБЛЕМ С МИГРАЦИЯМИ ==="

echo ""
echo "1. Проверка существующих миграций:"
find . -name "migrations" -type d -exec find {} -name "*.py" -not -name "__init__.py" \; | head -20

echo ""
echo "2. Проверка импортов в моделях:"
python manage.py check --deploy 2>&1

echo ""
echo "3. Попытка выполнить makemigrations с детальным выводом:"
python manage.py makemigrations --dry-run --verbosity=2 2>&1

echo ""
echo "4. Проверка модели Product в базе данных:"
python manage.py shell -c "
from inventory.models import Product
print('Product model fields:')
for field in Product._meta.fields:
    print(f'  {field.name}: {field.__class__.__name__}')
"

echo ""
echo "5. Проверка всех приложений на ошибки:"
python manage.py check inventory
python manage.py check stores
python manage.py check users 2>/dev/null || echo "users app не найден"
python manage.py check customers 2>/dev/null || echo "customers app не найден"
python manage.py check sales 2>/dev/null || echo "sales app не найден"

echo ""
echo "6. Проверка конфликтов в зависимостях моделей:"
python manage.py shell -c "
import django
from django.apps import apps
print('Загруженные приложения:')
for app in apps.get_app_configs():
    print(f'  {app.name}')
"