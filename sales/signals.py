# sales/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from sales.models import Transaction, TransactionItem
from analytics.models import SalesSummary, ProductAnalytics, CustomerAnalytics
from sales.models import TransactionHistory
import logging
import json

logger = logging.getLogger('analytics')

@receiver(post_save, sender=Transaction)
def update_sales_analytics(sender, instance, created, **kwargs):
    """
    Обновляет аналитику по продажам при создании или обновлении транзакции.
    """
    if instance.status != 'completed':
        return  # Обрабатываем только завершённые транзакции

    date = instance.created_at.date()
    payment_method = instance.payment_method

    # Обновляем или создаём сводку по продажам
    sales_summary, created = SalesSummary.objects.get_or_create(
        date=date,
        payment_method=payment_method,
        store=instance.store,  # ← ДОБАВЛЯЕМ store
        defaults={
            'total_amount': instance.total_amount,
            'total_transactions': 1,
            'total_items_sold': sum(item.quantity for item in instance.items.all()),
            'cashier': instance.cashier,
        }
    )
    if not created:
        sales_summary.total_amount += instance.total_amount
        sales_summary.total_transactions += 1
        sales_summary.total_items_sold += sum(item.quantity for item in instance.items.all())
        sales_summary.save()
        logger.info(f"Обновлена сводка продаж за {date} ({payment_method})")

    # Обновляем аналитику по товарам
    for item in instance.items.all():
        product_analytics, created = ProductAnalytics.objects.get_or_create(
            product=item.product,
            date=date,
            defaults={
                'quantity_sold': item.quantity,
                'revenue': item.quantity * item.price,
                'cashier': instance.cashier,
            }
        )
        if not created:
            product_analytics.quantity_sold += item.quantity
            product_analytics.revenue += item.quantity * item.price
            product_analytics.save()
            logger.info(f"Обновлена аналитика для {item.product.name} за {date}")

    # Обновляем аналитику по клиентам (если есть клиент)
    if instance.customer:
        customer_analytics, created = CustomerAnalytics.objects.get_or_create(
            customer=instance.customer,
            date=date,
            defaults={
                'total_purchases': instance.total_amount,
                'transaction_count': 1,
                'debt_added': instance.total_amount if instance.payment_method == 'debt' else 0,
                'cashier': instance.cashier,
            }
        )
        if not created:
            customer_analytics.total_purchases += instance.total_amount
            customer_analytics.transaction_count += 1
            if instance.payment_method == 'debt':
                customer_analytics.debt_added += instance.total_amount
            customer_analytics.save()
            logger.info(f"Обновлена аналитика для клиента {instance.customer.full_name} за {date}")

@receiver(post_save, sender=Transaction)
def update_transaction_history(sender, instance, created, **kwargs):
    """
    ИСПРАВЛЕННАЯ версия - создает записи только когда нужно и с правильным store
    """
    # Определяем действие
    if created:
        action = 'created'
    else:
        action = instance.status

    # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Проверяем не существует ли уже такая запись
    existing_record = TransactionHistory.objects.filter(
        transaction=instance,
        action=action
    ).first()

    if existing_record:
        # Запись уже есть - обновляем её данные вместо создания новой
        details = {
            'total_amount': str(instance.total_amount),
            'payment_method': instance.payment_method,
            'cashier': instance.cashier.username if instance.cashier else None,
            'customer': instance.customer.full_name if instance.customer else None,
            'items': [
                {
                    'product': item.product.name,
                    'quantity': item.quantity,
                    'price': str(item.price)
                }
                for item in instance.items.all()
            ]
        }
        existing_record.details = json.dumps(details, ensure_ascii=False)
        existing_record.save()
        return  # Выходим, не создаем новую запись

    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Создаем записи только для важных событий
    important_actions = ['created', 'completed', 'refunded']
    if action not in important_actions:
        return  # Пропускаем промежуточные статусы

    # ✅ ИСПРАВЛЕНИЕ: Проверяем что у транзакции есть store
    if not hasattr(instance, 'store') or not instance.store:
        logger.error(f"Transaction {instance.id} has no store, cannot create history")
        return

    # Создаем новую запись только если её еще нет
    details = {
        'total_amount': str(instance.total_amount),
        'payment_method': instance.payment_method,
        'cashier': instance.cashier.username if instance.cashier else None,
        'customer': instance.customer.full_name if instance.customer else None,
        'items': [
            {
                'product': item.product.name,
                'quantity': item.quantity,
                'price': str(item.price)
            }
            for item in instance.items.all()
        ]
    }

    # ✅ ИСПРАВЛЕНИЕ: Создаем запись с указанием store
    TransactionHistory.objects.create(
        transaction=instance,
        action=action,
        details=json.dumps(details, ensure_ascii=False),
        store=instance.store  # ← ДОБАВЛЯЕМ store!
    )

    logger.info(f"Created transaction history for transaction {instance.id} with action {action} in store {instance.store.name}")