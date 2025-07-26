# inventory/models.py
import logging
from django.db import models
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum, F

logger = logging.getLogger('inventory')

class MeasurementCategory(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Категория")  # Масса, Длина, Объем, Штука
    allow_fraction = models.BooleanField(default=False, verbose_name="Разрешить дробные значения")  # Можно ли дробные значения
    base_unit_name = models.CharField(max_length=20, verbose_name="Базовая единица")  # Например, кг, м, л

    class Meta:
        verbose_name = "Категория единиц измерения"
        verbose_name_plural = "Категории единиц измерения"
        ordering = ['name']

    def __str__(self):
        return self.name


class UnitOfMeasure(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Единица измерения")
    short_name = models.CharField(max_length=10, unique=True, verbose_name="Краткое название")
    category = models.ForeignKey('inventory.MeasurementCategory', on_delete=models.PROTECT, related_name='units')
    conversion_factor = models.DecimalField(max_digits=10, decimal_places=6, default=1.0, help_text="Коэффициент к базовой единице")

    is_active = models.BooleanField(default=True, verbose_name="Активна или нет")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Единица измерения"
        verbose_name_plural = "Единицы измерения"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.short_name})"

class ProductCategory(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Категория товара"
        verbose_name_plural = "Категории товаров"
        ordering = ['name']

    def __str__(self): 
        return self.name

class Product(models.Model):
    
    name = models.CharField(max_length=255, db_index=True)
    barcode = models.CharField(
        max_length=100, 
        unique=True, 
        null=True, 
        blank=True,
        db_index=True
    )
    category = models.ForeignKey(
        ProductCategory, 
        on_delete=models.PROTECT,
        related_name='products'
    )
    unit = models.ForeignKey(
        'inventory.UnitOfMeasure',
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name="Единица измерения"
        )
    
    sale_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00, 
        validators=[MinValueValidator(0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        indexes = [
            models.Index(fields=['name', 'barcode']),
        ]

    def __str__(self): 
        return f"{self.name} ({self.get_unit_display()})"

class ProductBatch(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='batches'
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    supplier = models.CharField(max_length=255, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Партия товара"
        verbose_name_plural = "Партии товаров"
        ordering = ['expiration_date', 'created_at']  # FIFO по умолчанию

    def sell(self, quantity):
        if quantity > self.quantity:
            raise ValueError(
                f"Недостаточно товара в партии. Доступно: {self.quantity}, запрошено: {quantity}"
            )
        self.quantity = F('quantity') - quantity
        self.save(update_fields=['quantity'])
        self.refresh_from_db()
        
        if self.quantity == 0:
            self.delete()
            logger.info(f"Партия {self.id} удалена (товар {self.product.name})")
        
        return quantity

    def __str__(self):
        return f"{self.product.name} × {self.quantity} (поставщик: {self.supplier})"

class Stock(models.Model):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='stock'
    )
    quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Остаток на складе"
        verbose_name_plural = "Остатки на складе"

    def update_quantity(self):
        """Обновляет общее количество товара на основе партий"""
        total = self.product.batches.aggregate(
            total=Sum('quantity')
        )['total'] or 0
        self.quantity = total
        self.save(update_fields=['quantity', 'updated_at'])

    def sell(self, quantity):
        """Списывает товар по FIFO с обработкой ошибок"""
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным")
            
        if self.quantity < quantity:
            raise ValueError(
                f"Недостаточно товара '{self.product.name}'. Доступно: {self.quantity}, запрошено: {quantity}"
            )

        remaining = quantity
        batches = self.product.batches.order_by('expiration_date', 'created_at')
        
        for batch in batches:
            if remaining <= 0:
                break
                
            sell_amount = min(remaining, batch.quantity)
            batch.sell(sell_amount)
            remaining -= sell_amount

        self.update_quantity()
        logger.info(f"Продано {quantity} {self.product.get_unit_display()} {self.product.name}")

    def __str__(self):
        return f"{self.product.name}: {self.quantity} {self.product.get_unit_display()}"

@receiver(post_save, sender=Product)
def create_product_stock(sender, instance, created, **kwargs):
    if created and not hasattr(instance, 'stock'):
        Stock.objects.create(product=instance)
        logger.info(f"Создан остаток для товара: {instance.name}")

@receiver(post_save, sender=ProductBatch)
def update_stock_on_batch_change(sender, instance, **kwargs):
    instance.product.stock.update_quantity()

