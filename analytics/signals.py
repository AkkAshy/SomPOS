# analytics/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from sales.models import Transaction, TransactionItem
from analytics.models import SalesSummary, ProductAnalytics, CustomerAnalytics
from sales.models import TransactionHistory
import logging

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
        store=instance.store,   # ✅ добавляем магазин
        date=date,
        payment_method=payment_method,
        defaults={
            'total_amount': instance.total_amount,
            'total_transactions': 1,
            'total_items_sold': sum(item.quantity for item in instance.items.all())
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
                'revenue': item.quantity * item.price
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
                'debt_added': instance.total_amount if instance.payment_method == 'debt' else 0
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
    action = 'created' if created else instance.status
    TransactionHistory.objects.create(
        transaction=instance,
        action=action,
        details=f"Транзакция {instance.id} {action} пользователем {instance.cashier.username}"
    )
    logger.info(f"Создана запись в истории для транзакции {instance.id}")