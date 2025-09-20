# signals.py — чистый, без self'а
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal
import logging
from inventory.models import StockHistory, Stock, SizeInfo, ProductBatch
from sales.models import TransactionItem, Transaction  # Твои импорты
from django.db.models import Sum, Count, F

logger = logging.getLogger(__name__)

@receiver(post_save, sender=TransactionItem)
def track_sales_from_transaction(sender, instance, created, **kwargs):
    """
    Каждая продажа → запись в StockHistory + обновление стока
    """
    if created and instance.transaction.status == 'completed':
        
        product = instance.product
        store = instance.store  # Из StoreOwnedModel
        transaction = instance.transaction
        
        # Получаем текущий сток ДО продажи
        stock, _ = Stock.objects.get_or_create(
            product=product, 
            store=store,
            defaults={'quantity': 0}
        )
        quantity_before = stock.quantity
        
        # Определяем размер из size_snapshot
        size_instance = None
        if instance.size_snapshot:
            size_id = instance.size_snapshot.get('id')
            if size_id:
                try:
                    size_instance = SizeInfo.objects.get(id=size_id)
                except SizeInfo.DoesNotExist:
                    logger.warning(f"Размер {size_id} из snapshot не найден")
        
        # Создаём запись истории стока
        StockHistory.objects.create(
            product=product,
            store=store,
            quantity_before=quantity_before,
            quantity_after=quantity_before - instance.quantity,
            quantity_change=-instance.quantity,  # Отрицательное для продаж
            operation_type='SALE',
            reference_id=f'txn_{transaction.id}_item_{instance.id}',
            user=transaction.cashier,  # Кассир
            size=size_instance,
            sale_price_at_time=instance.price,
            purchase_price_at_time=product.price_info['purchase_prices']['average'] if product.price_info else 0,
            notes=f'Продажа: кассир={transaction.cashier.username if transaction.cashier else "N/A"}, '
                  f'клиент={transaction.customer.name if transaction.customer else "N/A"}, '
                  f'метод={transaction.payment_method}, qty={instance.quantity}'
        )
        
        # Обновляем текущий сток
        stock.quantity -= instance.quantity
        stock.save(update_fields=['quantity'])
        
        # Логируем для дебага
        logger.info(
            f"✅ Продажа записана: {product.name} x{instance.quantity} "
            f"по {instance.price} (сток: {quantity_before} → {stock.quantity})"
        )
        
        # Обновляем атрибуты батча (если есть) — ВЫНЕСЛИ В ОТДЕЛЬНУЮ ФУНКЦИЮ
        update_batch_attributes_on_sale(product, instance.quantity, size_instance, store)

def update_batch_attributes_on_sale(product, sold_quantity, size_instance, store):
    """
    ✅ ОТДЕЛЬНАЯ ФУНКЦИЯ: Распределяем продажу по атрибутам батча
    """
    # Находим активные батчи с атрибутами
    active_batches = ProductBatch.objects.filter(
        product=product,
        store=store,
        quantity__gt=0
    ).select_related('attributes')
    
    if not active_batches.exists():
        logger.debug(f"Нет активных батчей для {product.name}")
        return
    
    # Распределяем пропорционально (простая логика)
    total_available = sum(batch.quantity for batch in active_batches)
    if total_available == 0:
        logger.warning(f"Общий доступный сток для {product.name} равен 0")
        return
    
    remaining_to_sell = sold_quantity
    for batch in active_batches:
        if remaining_to_sell <= 0:
            break
            
        batch_share = min(
            batch.quantity, 
            remaining_to_sell * (batch.quantity / total_available)
        )
        
        # Обновляем батч
        batch.quantity -= batch_share
        batch.save(update_fields=['quantity'])
        
        # Обновляем атрибуты батча
        updated_attrs = 0
        for batch_attr in batch.attributes.all():
            if batch_attr.quantity > 0:
                attr_share = min(
                    batch_attr.quantity, 
                    batch_share * (batch_attr.quantity / batch.quantity if batch.quantity else 0)
                )
                batch_attr.quantity -= attr_share
                batch_attr.save(update_fields=['quantity'])
                updated_attrs += 1
        
        remaining_to_sell -= batch_share
        logger.debug(
            f"Обновлён батч {batch.id}: -{batch_share}, "
            f"атрибутов обновлено: {updated_attrs}"
        )
    
    if remaining_to_sell > 0:
        logger.warning(
            f"Не удалось распределить всю продажу {sold_quantity} "
            f"для {product.name} — осталось {remaining_to_sell}"
        )

@receiver(post_save, sender=Transaction)
def track_transaction_financials(sender, instance, created, **kwargs):
    """
    ✅ Исправленная версия: анализируем гибридные оплаты
    """
    if created and instance.status == 'completed':
        # Вычисляем реальную сумму (для гибридной оплаты)
        actual_total = (
            instance.cash_amount + 
            instance.transfer_amount + 
            instance.card_amount
        )
        
        if abs(actual_total - instance.total_amount) > Decimal('0.01'):  # Допуск на копейки
            logger.warning(
                f"Несоответствие сумм в транзакции {instance.id}: "
                f"total_amount={instance.total_amount}, actual={actual_total}"
            )
            # Можно пометить как требующее проверки
            instance.needs_review = True  # Если добавишь такое поле
            instance.save(update_fields=['needs_review'])
        
        # Обновляем дневную финансовую сводку
        update_daily_financial_summary(instance)

def update_daily_financial_summary(transaction):
    """
    ✅ ОТДЕЛЬНАЯ ФУНКЦИЯ: обновляем дневную финансовую сводку
    """
    from django.db.models import Sum, Count, Avg
    from inventory.models import FinancialSummary
    
    today = transaction.created_at.date()
    store = transaction.store
    
    # Получаем или создаём сводку за день
    summary, created = FinancialSummary.objects.get_or_create(
        date=today,
        store=store,
        defaults={
            'cash_total': transaction.cash_amount,
            'transfer_total': transaction.transfer_amount,
            'card_total': transaction.card_amount,
            'debt_total': transaction.total_amount if transaction.payment_method == 'debt' else 0,
            'total_transactions': 1,
            'grand_total': transaction.total_amount,
            'avg_transaction': transaction.total_amount,
            # Маржинальность (пока грубо — позже посчитаем точно)
            'total_margin': 0,  # TODO: из TransactionItem
            'margin_percentage': 0,
        }
    )
    
    if not created:
        # Обновляем существующую сводку
        summary.cash_total += transaction.cash_amount
        summary.transfer_total += transaction.transfer_amount
        summary.card_total += transaction.card_amount
        summary.debt_total += transaction.total_amount if transaction.payment_method == 'debt' else 0
        summary.total_transactions += 1
        summary.grand_total += transaction.total_amount
        
        # Пересчитываем средний чек
        summary.avg_transaction = summary.grand_total / summary.total_transactions
        
        # Обновляем топ-кассира
        cashier_sales = Transaction.objects.filter(
            store=store,
            date=today,
            cashier=transaction.cashier,
            status='completed'
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        if cashier_sales > summary.top_cashier_sales:
            summary.top_cashier = transaction.cashier
            summary.top_cashier_sales = cashier_sales
        
        summary.save()
    
    logger.debug(
        f"Финансовая сводка обновлена: {store.name} | {today} | "
        f"чеков: {summary.total_transactions} | всего: {summary.grand_total}"
    )

# ✅ Дополнительный signal для отмены транзакции (если статус меняется на refunded)
@receiver(post_save, sender=Transaction)
def handle_transaction_refund(sender, instance, **kwargs):
    """
    Обработка возврата/отмены транзакции — возвращаем сток
    """
    if instance.status == 'refunded' and not hasattr(instance, '_original_status'):
        # Это возврат — возвращаем товары на склад
        
        for item in instance.items.all():
            # Возвращаем сток
            stock, _ = Stock.objects.get_or_create(
                product=item.product,
                store=instance.store
            )
            stock.quantity += item.quantity
            stock.save(update_fields=['quantity'])
            
            # Создаём запись возврата в истории
            StockHistory.objects.create(
                product=item.product,
                store=instance.store,
                quantity_before=stock.quantity - item.quantity,
                quantity_after=stock.quantity,
                quantity_change=item.quantity,  # Положительное для возврата
                operation_type='RETURN',
                reference_id=f'refund_{instance.id}_item_{item.id}',
                user=instance.cashier,
                size_id=item.size_snapshot.get('id') if item.size_snapshot else None,
                notes=f'Возврат по транзакции {instance.id}'
            )
            
            logger.info(
                f"✅ Возврат обработан: {item.product.name} x{item.quantity} "
                f"(сток: {stock.quantity - item.quantity} → {stock.quantity})"
            )
    
    # Сохраняем оригинальный статус для отслеживания изменений
    if not hasattr(instance, '_original_status'):
        instance._original_status = instance.status