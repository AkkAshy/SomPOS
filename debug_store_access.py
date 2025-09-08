# debug_store_access.py - поместите в корень проекта и запустите python debug_store_access.py

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sompos.settings")
django.setup()

from django.contrib.auth.models import User
from stores.models import Store, StoreEmployee
from inventory.models import Product
from customers.models import Customer
from sales.models import Transaction

def debug_store_access():
    print("=== ОТЛАДКА ДОСТУПА К МАГАЗИНАМ ===\n")

    # 1. Показать все магазины
    stores = Store.objects.all()
    print(f"📊 Всего магазинов: {stores.count()}")
    for store in stores:
        print(f"  🏪 {store.name} (ID: {store.id}, Owner: {store.owner.username})")

    # 2. Показать всех пользователей и их магазины
    users = User.objects.filter(store_memberships__isnull=False).distinct()
    print(f"\n👥 Пользователей с доступом к магазинам: {users.count()}")

    for user in users:
        print(f"\n  👤 {user.username}:")
        memberships = StoreEmployee.objects.filter(user=user)
        for membership in memberships:
            active = "✅" if membership.is_active else "❌"
            print(f"    {active} {membership.store.name} ({membership.role})")

    # 3. Проверить товары по магазинам
    print(f"\n📦 ТОВАРЫ ПО МАГАЗИНАМ:")
    for store in stores:
        products = Product.objects.filter(store=store)
        print(f"  🏪 {store.name}: {products.count()} товаров")
        if products.exists():
            for product in products[:3]:  # Показать первые 3
                print(f"    - {product.name} (ID: {product.id})")

    # 4. Проверить клиентов по магазинам
    print(f"\n👥 КЛИЕНТЫ ПО МАГАЗИНАМ:")
    for store in stores:
        customers = Customer.objects.filter(store=store)
        print(f"  🏪 {store.name}: {customers.count()} клиентов")
        if customers.exists():
            for customer in customers[:3]:  # Показать первых 3
                print(f"    - {customer.full_name} (ID: {customer.id})")

    # 5. Проверить продажи по магазинам
    print(f"\n💰 ПРОДАЖИ ПО МАГАЗИНАМ:")
    for store in stores:
        transactions = Transaction.objects.filter(store=store)
        print(f"  🏪 {store.name}: {transactions.count()} транзакций")

    # 6. КРИТИЧЕСКАЯ ПРОВЕРКА: Есть ли данные без магазина?
    print(f"\n🚨 ПРОВЕРКА НА ДАННЫЕ БЕЗ МАГАЗИНА:")

    products_without_store = Product.objects.filter(store__isnull=True)
    print(f"  📦 Товары без магазина: {products_without_store.count()}")
    if products_without_store.exists():
        print("    ⚠️ ПРОБЛЕМА! Найдены товары без магазина:")
        for product in products_without_store[:5]:
            print(f"      - {product.name} (ID: {product.id})")

    customers_without_store = Customer.objects.filter(store__isnull=True)
    print(f"  👥 Клиенты без магазина: {customers_without_store.count()}")
    if customers_without_store.exists():
        print("    ⚠️ ПРОБЛЕМА! Найдены клиенты без магазина:")
        for customer in customers_without_store[:5]:
            print(f"      - {customer.full_name} (ID: {customer.id})")

    transactions_without_store = Transaction.objects.filter(store__isnull=True)
    print(f"  💰 Транзакции без магазина: {transactions_without_store.count()}")
    if transactions_without_store.exists():
        print("    ⚠️ ПРОБЛЕМА! Найдены транзакции без магазина:")
        for transaction in transactions_without_store[:5]:
            print(f"      - Транзакция #{transaction.id} от {transaction.created_at}")

def test_specific_user_access(username):
    """Проверить доступ конкретного пользователя"""
    try:
        user = User.objects.get(username=username)
        print(f"\n🔍 ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ: {username}")

        # Магазины через StoreEmployee
        memberships = StoreEmployee.objects.filter(user=user, is_active=True)
        print(f"  Доступных магазинов: {memberships.count()}")

        accessible_stores = []
        for membership in memberships:
            accessible_stores.append(membership.store)
            print(f"    🏪 {membership.store.name} ({membership.role})")

        # Проверяем что видит этот пользователь
        if accessible_stores:
            first_store = accessible_stores[0]
            print(f"\n  📦 Товары в первом магазине ({first_store.name}):")
            products = Product.objects.filter(store=first_store)
            print(f"    Количество: {products.count()}")

            print(f"\n  📦 Товары БЕЗ фильтра по магазину:")
            all_products = Product.objects.all()
            print(f"    Общее количество: {all_products.count()}")

            if products.count() != all_products.count():
                print("    ✅ Фильтрация работает корректно")
            else:
                print("    ❌ ПРОБЛЕМА: Пользователь видит ВСЕ товары!")

                # Показать товары других магазинов
                other_stores = Store.objects.exclude(id=first_store.id)
                for other_store in other_stores:
                    other_products = Product.objects.filter(store=other_store)
                    if other_products.exists():
                        print(f"      🚨 Товары магазина {other_store.name}: {other_products.count()}")

    except User.DoesNotExist:
        print(f"❌ Пользователь '{username}' не найден")

if __name__ == "__main__":
    debug_store_access()

    # Проверить конкретных пользователей
    print("\n" + "="*50)
    test_specific_user_access("testadmin")  # Замените на реального пользователя

    # Можете добавить других пользователей
    # test_specific_user_access("другой_админ")