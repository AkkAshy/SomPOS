# inventory/signals.py - ИСПРАВЛЕННАЯ ВЕРСИЯ БЕЗ ДУБЛИРОВАНИЯ
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal
import logging
from inventory.models import StockHistory, Stock, SizeInfo, ProductBatch, FinancialSummary
from analytics.models import CashRegister, CashHistory
from sales.models import TransactionItem, Transaction
from django.db.models import Sum, Count, F

logger = logging.getLogger(__name__)

print("🔄 Loading inventory signals...")


@receiver(pre_save, sender=Transaction)
def track_original_status(sender, instance, **kwargs):
    """
    Сохраняем старый статус перед изменением
    """
    if instance.pk:
        try:
            old = Transaction.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except Transaction.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Transaction)
def handle_transaction_complete(sender, instance, created, **kwargs):
    """
    ✅ ЕДИНСТВЕННЫЙ сигнал для Transaction - обрабатывает ВСЁ
    """
    old_status = getattr(instance, "_old_status", None)
    
    print(f"🔔 Transaction signal ID={instance.id}, created={created}, status={instance.status}, old_status={old_status}, cash={instance.cash_amount}")
    
    # Определяем, стала ли транзакция completed
    became_completed = False
    
    if created and instance.status == "completed":
        became_completed = True
        print(f"✅ New completed transaction {instance.id}")
    elif not created and old_status != "completed" and instance.status == "completed":
        became_completed = True
        print(f"✅ Transaction became completed: {instance.id}")
    
    if became_completed:
        # 1. Обновляем кассу при наличной оплате
        if instance.cash_amount > 0:
            print(f"💰 Processing cash {instance.cash_amount}")
            update_cash_register_on_sale(instance)
        else:
            print(f"💳 No cash in transaction")
        
        # 2. Обновляем дневную финансовую сводку
        update_daily_financial_summary(instance)
        
        # 3. Проверяем соответствие сумм
        actual_total = instance.cash_amount + instance.transfer_amount + instance.card_amount
        if abs(actual_total - instance.total_amount) > Decimal('0.01'):
            logger.warning(f"Несоответствие сумм в транзакции {instance.id}: total={instance.total_amount}, actual={actual_total}")
    
    # Обрабатываем возвраты
    if instance.status == 'refunded' and old_status != 'refunded':
        print(f"🔄 Processing refund for transaction {instance.id}")
        handle_transaction_refund(instance)


@receiver(post_save, sender=TransactionItem)
def track_sales_from_transaction(sender, instance, created, **kwargs):
    """
    Каждая продажа → запись в StockHistory + обновление стока
    """
    if created and instance.transaction.status == 'completed':
        
        product = instance.product
        store = instance.store
        transaction = instance.transaction
        
        print(f"📦 Processing sale: {product.name} x{instance.quantity} in {store.name}")
        
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
        
        # ✅ БЕЗОПАСНАЯ строка без двоеточий
        safe_notes = f'Продажа номер {transaction.id} количество {float(instance.quantity)} товар {product.name}'
        
        # Создаём запись истории стока
        StockHistory.objects.create(
            product=product,
            store=store,
            quantity_before=quantity_before,
            quantity_after=quantity_before - instance.quantity,
            quantity_change=-instance.quantity,
            operation_type='SALE',
            reference_id=f'txn_{transaction.id}_item_{instance.id}',
            user=transaction.cashier,
            size=size_instance,
            sale_price_at_time=instance.price,
            purchase_price_at_time=product.price_info['purchase_prices']['average'] if product.price_info else 0,
            notes=safe_notes  # ✅ Исправленная строка
        )
        
        # Обновляем текущий сток
        stock.quantity -= instance.quantity
        stock.save(update_fields=['quantity'])
        
        logger.info(f"✅ Sale processed: {product.name} stock {quantity_before} → {stock.quantity}")
        print(f"✅ Stock updated: {quantity_before} → {stock.quantity}")
        
        # Обновляем атрибуты батча
        update_batch_attributes_on_sale(product, instance.quantity, size_instance, store)



def update_cash_register_on_sale(transaction):
    """
    ✅ Обновление кассы при продаже наличными
    """
    store = transaction.store
    cash_amount = transaction.cash_amount
    
    print(f"💰 Updating cash register: store={store.name}, amount={cash_amount}")
    
    if cash_amount <= 0:
        print("💰 No cash to process")
        return
    
    try:
        # Ищем открытую кассу для магазина сегодня
        today = timezone.now().date()
        cash_register = CashRegister.objects.filter(
            store=store,
            date_opened__date=today,
            is_open=True
        ).first()
        
        # Если нет открытой кассы - создаём новую
        if not cash_register:
            print(f"💰 Creating new cash register for {store.name}")
            cash_register = CashRegister.objects.create(
                store=store,
                current_balance=Decimal('0.00'),
                target_balance=Decimal('0.00'),
                is_open=True,
                date_opened=timezone.now()
            )
            print(f"💰 Created cash register ID: {cash_register.id}")
        
        # Проверяем, не обработана ли уже эта транзакция
        existing_history = CashHistory.objects.filter(
            cash_register=cash_register,
            notes__contains=f"#{transaction.id}",
            operation_type='ADD_CASH'
        ).exists()
        
        if existing_history:
            print(f"💰 Transaction {transaction.id} already processed in cash register")
            return
        
        # Сохраняем баланс до операции
        balance_before = cash_register.current_balance
        
        # ✅ ПРЯМОЕ обновление баланса (избегаем метод add_cash для простоты)
        cash_register.current_balance += cash_amount
        cash_register.save(update_fields=['current_balance', 'last_updated'])
        
        # Создаём запись в истории кассы
        CashHistory.objects.create(
            cash_register=cash_register,
            operation_type='ADD_CASH',
            amount=cash_amount,
            user=transaction.cashier,
            store=store,
            notes=f"Продажа {transaction.id}",
            balance_before=balance_before,
            balance_after=cash_register.current_balance
        )
        
        print(f"💰 Cash register updated: {balance_before} → {cash_register.current_balance}")
        logger.info(f"✅ Cash register updated: +{cash_amount}, balance: {cash_register.current_balance}")
        
    except Exception as e:
        logger.error(f"❌ Error updating cash register: {e}")
        print(f"❌ Cash register error: {e}")
        import traceback
        print(traceback.format_exc())


def update_daily_financial_summary(transaction):
    """
    ✅ Обновляем дневную финансовую сводку
    """
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
            'total_margin': 0,
            'margin_percentage': 0,
        }
    )
    
    if not created:
        # Обновляем существующую сводку
        summary.cash_total += transaction.cash_amount
        summary.transfer_total += transaction.transfer_amount
        summary.card_total += transaction.card_amount
        if transaction.payment_method == 'debt':
            summary.debt_total += transaction.total_amount
        summary.total_transactions += 1
        summary.grand_total += transaction.total_amount
        summary.avg_transaction = summary.grand_total / summary.total_transactions
        summary.save()
    
    logger.debug(f"Financial summary updated for {store.name} on {today}")


def handle_transaction_refund(transaction):
    """
    ✅ Обработка возврата транзакции
    """
    # Возвращаем товары на склад
    for item in transaction.items.all():
        stock, _ = Stock.objects.get_or_create(
            product=item.product,
            store=transaction.store,
            defaults={'quantity': 0}
        )
        
        old_quantity = stock.quantity
        stock.quantity += item.quantity
        stock.save(update_fields=['quantity'])
        
        # ✅ БЕЗОПАСНАЯ строка без двоеточий
        safe_refund_notes = f'Возврат по транзакции номер {transaction.id}'
        
        # Создаём запись возврата в истории
        StockHistory.objects.create(
            product=item.product,
            store=transaction.store,
            quantity_before=old_quantity,
            quantity_after=stock.quantity,
            quantity_change=item.quantity,
            operation_type='RETURN',
            reference_id=f'refund_{transaction.id}_item_{item.id}',
            user=transaction.cashier,
            notes=safe_refund_notes  # ✅ Исправленная строка
        )
    
    # Возвращаем наличные из кассы
    if transaction.cash_amount > 0:
        handle_cash_refund(transaction)


def handle_cash_refund(transaction):
    """
    ✅ Возврат наличных из кассы
    """
    store = transaction.store
    refund_amount = transaction.cash_amount
    
    today = timezone.now().date()
    cash_register = CashRegister.objects.filter(
        store=store,
        date_opened__date=today,
        is_open=True
    ).first()
    
    if not cash_register:
        logger.error(f"No open cash register for refund {refund_amount}")
        return
    
    try:
        if cash_register.current_balance >= refund_amount:
            balance_before = cash_register.current_balance
            cash_register.current_balance -= refund_amount
            cash_register.save(update_fields=['current_balance', 'last_updated'])
            
            CashHistory.objects.create(
                cash_register=cash_register,
                operation_type='WITHDRAW',
                amount=refund_amount,
                user=transaction.cashier,
                store=store,
                notes=f"Возврат по транзакции {transaction.id}",
                balance_before=balance_before,
                balance_after=cash_register.current_balance
            )
            
            logger.info(f"Cash refund processed: -{refund_amount}")
        else:
            logger.error(f"Insufficient cash for refund: need {refund_amount}, have {cash_register.current_balance}")
    except Exception as e:
        logger.error(f"Error processing cash refund: {e}")


def update_batch_attributes_on_sale(product, sold_quantity, size_instance, store):
    """
    ✅ Распределяем продажу по атрибутам батча
    """
    active_batches = ProductBatch.objects.filter(
        product=product,
        store=store,
        quantity__gt=0
    )
    
    if not active_batches.exists():
        return
    
    total_available = sum(batch.quantity for batch in active_batches)
    if total_available == 0:
        return
    
    remaining_to_sell = sold_quantity
    for batch in active_batches:
        if remaining_to_sell <= 0:
            break
            
        batch_share = min(batch.quantity, remaining_to_sell)
        batch.quantity -= batch_share
        batch.save(update_fields=['quantity'])
        remaining_to_sell -= batch_share


print("✅ Inventory signals loaded successfully")