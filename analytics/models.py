# analytics/models.py - ОБНОВЛЕННАЯ ВЕРСИЯ
from django.db import models
from django.utils.translation import gettext_lazy as _
from inventory.models import Product, ProductCategory
from sales.models import Transaction
from customers.models import Customer
import logging
from django.contrib.auth.models import User
from stores.mixins import StoreOwnedModel, StoreOwnedManager


logger = logging.getLogger('analytics')

class SalesSummaryManager(StoreOwnedManager):
    def update_from_transaction(self, transaction):
        summary, created = self.get_or_create(
            store=transaction.store,
            date=transaction.created_at.date(),
            payment_method=transaction.payment_method,
            defaults={
                "cashier": transaction.cashier,
                "total_amount": transaction.total_amount,
                "total_transactions": 1,
                "total_items_sold": transaction.items_count,
            }
        )
        if not created:
            summary.total_amount += transaction.total_amount
            summary.total_transactions += 1
            summary.total_items_sold += transaction.items_count
            summary.save()
        return summary


class SalesSummary(StoreOwnedModel):
    date = models.DateField(verbose_name=_("Дата"))
    cashier = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Кассир",
        related_name="sales_summaries"
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_transactions = models.PositiveIntegerField(default=0)
    total_items_sold = models.PositiveIntegerField(default=0)
    payment_method = models.CharField(
        max_length=20, choices=Transaction.PAYMENT_METHODS
    )

    objects = SalesSummaryManager()

    class Meta:
        verbose_name = _("Сводка по продажам")
        verbose_name_plural = _("Сводки по продажам")
        unique_together = ('store', 'date', 'payment_method')
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - {self.get_payment_method_display()} ({self.total_amount})"


class ProductAnalytics(models.Model):
    """
    ОБНОВЛЕННАЯ статистика по товарам с учетом новой структуры товаров
    """
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='analytics',
        verbose_name=_("Товар")
    )
    cashier = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="product_analytics"
    )
    date = models.DateField(verbose_name=_("Дата"))
    quantity_sold = models.DecimalField(
        max_digits=15,  # Увеличено для поддержки дробных единиц
        decimal_places=3,  # Поддержка до тысячных
        default=0,
        verbose_name=_("Продано единиц")
    )
    revenue = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        verbose_name=_("Выручка")
    )
    
    # Новые поля для анализа единиц измерения
    unit_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Тип единицы измерения"
    )
    unit_display = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Отображение единицы"
    )
    
    # Информация о размере (если применимо)
    size_info = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Информация о размере",
        help_text="JSON с данными о размере товара на момент продажи"
    )
    
    # Средняя цена за единицу
    average_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Средняя цена за единицу"
    )

    class Meta:
        verbose_name = _("Аналитика товара")
        verbose_name_plural = _("Аналитика товаров")
        unique_together = ('product', 'date')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date', 'product']),
            models.Index(fields=['unit_type', 'date']),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.date} ({self.quantity_sold} {self.unit_display})"

    def save(self, *args, **kwargs):
        """Автоматически заполняем информацию о единицах при сохранении"""
        if self.product:
            self.unit_type = self.product.unit_type or 'custom'
            self.unit_display = self.product.unit_display
            
            # Сохраняем информацию о размере
            if self.product.has_sizes and self.product.default_size:
                self.size_info = {
                    'size': self.product.default_size.size,
                    'dimension1': float(self.product.default_size.dimension1) if self.product.default_size.dimension1 else None,
                    'dimension2': float(self.product.default_size.dimension2) if self.product.default_size.dimension2 else None,
                    'dimension3': float(self.product.default_size.dimension3) if self.product.default_size.dimension3 else None,
                    'dimension1_label': self.product.default_size.dimension1_label,
                    'dimension2_label': self.product.default_size.dimension2_label,
                    'dimension3_label': self.product.default_size.dimension3_label,
                }
            
            # Рассчитываем среднюю цену за единицу
            if self.quantity_sold and self.quantity_sold > 0:
                self.average_unit_price = self.revenue / self.quantity_sold
        
        super().save(*args, **kwargs)


class CustomerAnalytics(models.Model):
    """
    Статистика по клиентам
    """
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='analytics',
        verbose_name=_("Клиент")
    )
    cashier = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="customer_analytics"
    )
    date = models.DateField(verbose_name=_("Дата"))
    total_purchases = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        verbose_name=_("Сумма покупок")
    )
    transaction_count = models.PositiveIntegerField(
        default=0, verbose_name=_("Количество транзакций")
    )
    debt_added = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        verbose_name=_("Добавлено долга")
    )

    class Meta:
        verbose_name = _("Аналитика клиента")
        verbose_name_plural = _("Аналитика клиентов")
        unique_together = ('customer', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.customer.full_name} - {self.date} ({self.total_purchases})"


class UnitAnalytics(StoreOwnedModel):
    """
    НОВАЯ модель: Аналитика по единицам измерения
    """
    date = models.DateField(verbose_name=_("Дата"))
    unit_type = models.CharField(
        max_length=50,
        verbose_name="Тип единицы измерения"
    )
    unit_display = models.CharField(
        max_length=20,
        verbose_name="Отображение единицы"
    )
    is_custom = models.BooleanField(
        default=False,
        verbose_name="Пользовательская единица"
    )
    
    # Статистика продаж
    total_quantity_sold = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        default=0,
        verbose_name="Общее количество проданного"
    )
    total_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Общая выручка"
    )
    products_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество товаров с этой единицей"
    )
    transactions_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество транзакций"
    )
    
    # Средние показатели
    average_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Средняя цена за единицу"
    )

    objects = StoreOwnedManager()

    class Meta:
        verbose_name = _("Аналитика единиц измерения")
        verbose_name_plural = _("Аналитика единиц измерения")
        unique_together = ('store', 'date', 'unit_type', 'unit_display')
        ordering = ['-date', 'unit_display']

    def __str__(self):
        return f"{self.unit_display} - {self.date} ({self.total_quantity_sold})"

    def calculate_metrics(self):
        """Рассчитывает производные метрики"""
        if self.total_quantity_sold and self.total_quantity_sold > 0:
            self.average_unit_price = self.total_revenue / self.total_quantity_sold


class SizeAnalytics(StoreOwnedModel):
    """
    НОВАЯ модель: Аналитика по размерам товаров
    """
    date = models.DateField(verbose_name=_("Дата"))
    size_name = models.CharField(
        max_length=50,
        verbose_name="Название размера"
    )
    
    # Параметры размера на момент анализа
    dimension1 = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Параметр 1"
    )
    dimension2 = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Параметр 2"  
    )
    dimension3 = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Параметр 3"
    )
    
    # Метки параметров
    dimension1_label = models.CharField(max_length=50, null=True, blank=True)
    dimension2_label = models.CharField(max_length=50, null=True, blank=True)
    dimension3_label = models.CharField(max_length=50, null=True, blank=True)
    
    # Статистика продаж
    total_quantity_sold = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        default=0,
        verbose_name="Общее количество проданного"
    )
    total_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Общая выручка"
    )
    products_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество товаров этого размера"
    )
    transactions_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество транзакций"
    )

    objects = StoreOwnedManager()

    class Meta:
        verbose_name = _("Аналитика размеров")
        verbose_name_plural = _("Аналитика размеров")
        unique_together = ('store', 'date', 'size_name')
        ordering = ['-date', 'size_name']

    def __str__(self):
        return f"{self.size_name} - {self.date} ({self.total_quantity_sold})"

    @property
    def full_description(self):
        """Полное описание размера с параметрами"""
        parts = [self.size_name]
        
        if self.dimension1 and self.dimension1_label:
            parts.append(f"{self.dimension1_label}: {self.dimension1}")
        if self.dimension2 and self.dimension2_label:
            parts.append(f"{self.dimension2_label}: {self.dimension2}")
        if self.dimension3 and self.dimension3_label:
            parts.append(f"{self.dimension3_label}: {self.dimension3}")
            
        return " | ".join(parts)


class CategoryAnalytics(StoreOwnedModel):
    """
    НОВАЯ модель: Аналитика по категориям товаров
    """
    date = models.DateField(verbose_name=_("Дата"))
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.CASCADE,
        related_name='analytics',
        verbose_name=_("Категория")
    )
    
    # Статистика продаж
    total_quantity_sold = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        default=0,
        verbose_name="Общее количество проданного"
    )
    total_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Общая выручка"
    )
    products_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество товаров в категории"
    )
    transactions_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество транзакций"
    )
    unique_products_sold = models.PositiveIntegerField(
        default=0,
        verbose_name="Уникальных товаров продано"
    )
    
    # Средние показатели
    average_transaction_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Средняя сумма транзакции"
    )

    objects = StoreOwnedManager()

    class Meta:
        verbose_name = _("Аналитика категорий")
        verbose_name_plural = _("Аналитика категорий")
        unique_together = ('store', 'date', 'category')
        ordering = ['-date', 'category__name']

    def __str__(self):
        return f"{self.category.name} - {self.date} ({self.total_revenue})"

    def calculate_metrics(self):
        """Рассчитывает производные метрики"""
        if self.transactions_count > 0:
            self.average_transaction_amount = self.total_revenue / self.transactions_count



class SupplierAnalytics(StoreOwnedModel):
    """
    Аналитика по поставщикам — кто приносит прибыль, а кто убытки
    """
    date = models.DateField(verbose_name=_("Дата"))
    supplier = models.CharField(
        max_length=255,  # Как в ProductBatch
        verbose_name=_("Поставщик"),
        db_index=True  # Для быстрых поисков
    )
    
    # Статистика продаж (из StockHistory/Transactions)
    total_quantity_sold = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        default=0,
        verbose_name="Общее количество проданного"
    )
    total_revenue = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Общая выручка"
    )
    total_cost = models.DecimalField(  # Себестоимость проданного
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Общая себестоимость"
    )
    total_margin = models.DecimalField(  # Маржа = revenue - cost
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Общая маржа"
    )
    products_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество товаров от поставщика"
    )
    transactions_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество транзакций"
    )
    unique_products_sold = models.PositiveIntegerField(
        default=0,
        verbose_name="Уникальных товаров продано"
    )
    
    # Средние показатели
    average_margin_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Средняя маржа (%)"
    )
    turnover_rate = models.DecimalField(  # Оборачиваемость: sold / average_stock
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Коэффициент оборачиваемости"
    )

    objects = StoreOwnedManager()

    class Meta:
        verbose_name = _("Аналитика поставщиков")
        verbose_name_plural = _("Аналитика поставщиков")
        unique_together = ('store', 'date', 'supplier')
        ordering = ['-date', 'supplier']
        indexes = [
            models.Index(fields=['supplier', 'date']),
        ]

    def __str__(self):
        return f"{self.supplier} - {self.date} (Выручка: {self.total_revenue}, Маржа: {self.total_margin})"

    def calculate_metrics(self):
        """Рассчитывает производные метрики перед сохранением"""
        if self.total_revenue > 0:
            self.average_margin_percentage = (self.total_margin / self.total_revenue * 100)
        if self.products_count > 0:  # Примерный turnover; адаптируй под реальный average_stock из Stock
            average_stock = self.products_count  # Замени на реальный расчёт, если есть данные
            self.turnover_rate = self.total_quantity_sold / average_stock if average_stock else 0