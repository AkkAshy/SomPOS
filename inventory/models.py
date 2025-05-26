# inventory/models.py
import logging
from django.db import models
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum

logger = logging.getLogger('inventory')

class ProductCategory(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class Product(models.Model):
    UNIT_CHOICES = [('piece', 'Штука'), ('kg', 'Килограмм'), ('liter', 'Литр')]
    name = models.CharField(max_length=255)
    barcode = models.CharField(max_length=100, unique=True, null=True, blank=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT)
    unit = models.CharField(max_length=50, choices=UNIT_CHOICES, default='piece')
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        logger.debug(f"[SomPOS] Saving product: {self.name}")
        super().save(*args, **kwargs)
        logger.info(f"[SomPOS] Product saved: {self.name}")
    
    def __str__(self): return self.name

class ProductBatch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    expiration_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def sell(self, quantity):
        """Списывает указанное количество из партии, возвращает остаток"""
        if quantity > self.quantity:
            raise ValueError(f"Недостаточно товара в партии: {self.quantity} < {quantity}")
        self.quantity -= quantity
        if self.quantity == 0:
            self.delete()
            logger.info(f"[SomPOS] Deleted empty batch for {self.product.name}")
        else:
            self.save()
            logger.info(f"[SomPOS] Sold {quantity} from batch for {self.product.name}, remaining: {self.quantity}")
        return quantity
    
    def save(self, *args, **kwargs):
        logger.debug(f"[SomPOS] Saving batch for {self.product.name}: {self.quantity}")
        super().save(*args, **kwargs)
        logger.info(f"[SomPOS] Batch saved for {self.product.name}: {self.quantity}, expires: {self.expiration_date}")
        self.product.stock.update_quantity()
    
    def __str__(self): return f"{self.product.name}: {self.quantity} (Expires: {self.expiration_date})"

class Stock(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, unique=True)
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    updated_at = models.DateTimeField(auto_now=True)
    
    def update_quantity(self):
        total = self.product.batches.aggregate(total=Sum('quantity'))['total'] or 0
        self.quantity = total
        self.save()
    
    def sell(self, quantity):
        """Списывает количество из партий по FIFO"""
        if self.quantity < quantity:
            raise ValueError(f"Недостаточно товара на складе: {self.quantity} < {quantity}")
        remaining = quantity
        batches = self.product.batches.order_by('created_at', 'expiration_date')  # FIFO
        for batch in batches:
            if remaining <= 0:
                break
            sold = min(remaining, batch.quantity)
            batch.sell(sold)
            remaining -= sold
        self.update_quantity()
        logger.info(f"[SomPOS] Sold {quantity} of {self.product.name}, stock now: {self.quantity}")
    
    def save(self, *args, **kwargs):
        logger.debug(f"[SomPOS] Updating stock for {self.product.name}: {self.quantity}")
        super().save(*args, **kwargs)
        logger.info(f"[SomPOS] Stock updated for {self.product.name}: {self.quantity}")
    
    def __str__(self): return f"{self.product.name}: {self.quantity}"

@receiver(post_save, sender=Product)
def create_stock(sender, instance, created, **kwargs):
    if created:
        Stock.objects.create(product=instance)
        logger.info(f"[SomPOS] Created stock for product: {instance.name}")