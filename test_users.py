# test_users.py - проверим конкретных пользователей

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sompos.settings")
django.setup()

from django.contrib.auth.models import User
from stores.models import Store, StoreEmployee
from inventory.models import Product
from customers.models import Customer
from sales.models import Transaction

def test_user_access(username):
    """Детальная проверка доступа пользователя"""
    try:
        user = User.objects.get(username=username)
        print(f"\n🔍 ТЕСТ ПОЛЬЗОВАТЕЛЯ: {username}")
        print(f"  ID: {user.id}")
        print(f"  Группы: {list(user.groups.values_list('name', flat=True))}")
        print(f"  Суперпользователь: {user.is_superuser}")

        # Получаем доступные магазины
        memberships = StoreEmployee.objects.filter(user=user, is_active=True)
        print(f"  Доступных магазинов: {memberships.count()}")

        accessible_stores = []
        for membership in memberships:
            accessible_stores.append(membership.store)
            print(f"    🏪 {membership.store.name} (роль: {membership.role})")

        if not accessible_stores:
            print("  ❌ Пользователь не имеет доступа ни к одному магазину")
            return

        # Берем первый магазин как текущий
        current_store = accessible_stores[0]
        print(f"\n  📋 ПРОВЕРКА ДОСТУПА К ДАННЫМ (магазин: {current_store.name}):")

        # Товары в его магазине
        user_products = Product.objects.filter(store=current_store)
        print(f"    📦 Товары в своем магазине: {user_products.count()}")

        # ВСЕ товары в системе
        all_products = Product.objects.all()
        print(f"    📦 Всего товаров в системе: {all_products.count()}")

        # Товары в других магазинах
        other_stores = Store.objects.exclude(id=current_store.id)
        for other_store in other_stores:
            other_products = Product.objects.filter(store=other_store)
            if other_products.count() > 0:
                print(f"    🚨 Товары в чужом магазине '{other_store.name}': {other_products.count()}")
                # Показать первые 3 товара
                for product in other_products[:3]:
                    print(f"      - {product.name} (ID: {product.id})")

        # Проверим что происходит БЕЗ фильтрации
        print(f"\n  🔧 СИМУЛЯЦИЯ ЗАПРОСА БЕЗ ФИЛЬТРАЦИИ:")
        print(f"    Если пользователь получит ВСЕ товары: {all_products.count()}")

        # Проверим есть ли проблема с Employee
        if hasattr(user, 'employee'):
            employee = user.employee
            print(f"\n  👤 EMPLOYEE INFO:")
            print(f"    Основной магазин: {employee.store.name if employee.store else 'Не указан'}")
            print(f"    Доступные магазины: {employee.accessible_stores.count()}")
            for store in employee.accessible_stores.all():
                print(f"      - {store.name}")
        else:
            print(f"\n  ⚠️ У пользователя нет записи Employee")

    except User.DoesNotExist:
        print(f"❌ Пользователь '{username}' не найден")

# Тестируем всех активных пользователей
def test_all_active_users():
    print("🧪 ТЕСТ ВСЕХ АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ:")

    active_users = ['Shukurullo', 'akhmet08', 'azamat', 'Azaazaaza', 'akkanat223', 'axmet']

    for username in active_users:
        test_user_access(username)
        print("-" * 60)

if __name__ == "__main__":
    test_all_active_users()