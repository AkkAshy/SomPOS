import logging
from django.db import models
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum, F
from django.utils.text import format_lazy
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import barcode
from barcode.writer import ImageWriter
import os
from PIL import Image as PILImage, ImageDraw, ImageFont
from django.conf import settings
from reportlab.lib.pagesizes import A6
from reportlab.platypus import Image
from io import BytesIO
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping


pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
addMapping('DejaVuSans', 0, 0, 'DejaVuSans')
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('inventory')


class SizeInfo(models.Model):
    SIZE_CHOICES = [
        ('S', 'S'),
        ('M', 'M'),
        ('L', 'L'),
        ('XL', 'XL'),
        ('XXL', 'XXL'),
    ]



    size = models.CharField(max_length=50, verbose_name="Размер")

    chest = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        null=True,
        blank=True,
        verbose_name="Обхват груди"
    )
    waist = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        null=True,
        blank=True,
        verbose_name="Обхват талии"
    )
    length = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        null=True,
        blank=True,
        verbose_name="Длина"
    )


    class Meta:
        verbose_name = "Размерная информация"
        verbose_name_plural = "Размерные информации"
        unique_together = ('size',)

    def __str__(self):
        return f"{self.size}"


class ProductCategory(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Название")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Категория товара"
        verbose_name_plural = "Категории товаров"
        ordering = ['name']

    def __str__(self):
        return self.name


class AttributeType(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="Слаг")
    is_filterable = models.BooleanField(default=False, verbose_name="Фильтруемый ли?")

    class Meta:
        verbose_name = "Тип атрибута"
        verbose_name_plural = "Типы атрибутов"
        ordering = ['name']

    def __str__(self):
        return self.name


class AttributeValue(models.Model):
    attribute_type = models.ForeignKey(
        AttributeType,
        on_delete=models.CASCADE,
        related_name='values',
        verbose_name="Тип атрибута"

    )
    value = models.CharField(max_length=225, verbose_name="Значение")
    slug = models.SlugField(max_length=225, unique=True, verbose_name="Слаг")
    ordering = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Значение атрибута"
        verbose_name_plural = "Значения атрибутов"
        ordering = ['ordering', 'value']
        unique_together = ('attribute_type', 'slug')

    def __str__(self):
        return f"{self.attribute_type.name}: {self.value} ({self.slug})"

class Product(models.Model):
    UNIT_CHOICES = [
        ('piece', 'Штука')
    ]
    name = models.CharField(max_length=255, verbose_name="Название")


    barcode = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Штрих-код"
    )
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name="Категория"
    )
    unit = models.CharField(
        max_length=50,
        choices=UNIT_CHOICES,
        default='piece',
        verbose_name="Единица измерения"
    )
    sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)],
        verbose_name="Цена продажи"
    )
    attributes = models.ManyToManyField(
        AttributeValue,
        blank=True,
        related_name='products',
        verbose_name="Атрибуты"
    )
    size = models.ForeignKey(SizeInfo, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    image_label = models.ImageField(
        upload_to='product_labels/',
        null=True,
        blank=True,
        verbose_name="Изображение этикетки"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products_created',
        verbose_name="Создан пользователем"
    )

    @classmethod
    def generate_unique_barcode(cls):
        """
        Генерирует уникальный штрих-код для товара
        """
        import random
        import time
        from django.utils import timezone

        max_attempts = 100
        attempts = 0

        while attempts < max_attempts:
            # Вариант 1: На основе времени и случайных чисел
            timestamp = str(int(timezone.now().timestamp()))[-6:]  # 6 последних цифр времени
            random_part = str(random.randint(100000, 999999))  # 6 случайных цифр
            barcode = timestamp + random_part

            # Проверяем уникальность
            if not cls.objects.filter(barcode=barcode).exists():
                return barcode

            attempts += 1

        # Если не удалось сгенерировать за 100 попыток, используем UUID
        import uuid
        return str(uuid.uuid4().int)[:12]  # Первые 12 цифр из UUID

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        indexes = [
            models.Index(fields=['name', 'barcode']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_unit_display()})"


    def clean(self):
        """Валидация перед сохранением"""
        super().clean()
        if self.barcode:
            # Проверяем, что штрих-код состоит только из цифр
            barcode_str = str(self.barcode).strip()
            if not barcode_str.isdigit():
                raise ValidationError({'barcode': "Штрих-код должен содержать только цифры."})

    def generate_label(self):
        """Основной метод генерации этикетки без временных файлов"""
        if not self.barcode:
            logger.warning("Штрих-код отсутствует - этикетка не будет создана")
            return False

        try:
            # 1. Генерируем штрих-код в памяти
            barcode_image = self._generate_barcode_image()

            # 2. Создаем полную этикетку
            label_bytes = self._create_label_image(barcode_image)

            # 3. Сохраняем этикетку (ИСПРАВЛЕНО: используем правильное имя поля)
            label_filename = f'product_labels/product_{self.id}_label.png'
            self.image_label.save(label_filename, ContentFile(label_bytes), save=False)

            # Сохраняем только поле image_label, чтобы не вызвать рекурсию
            super().save(update_fields=['image_label'])

            logger.info(f"Этикетка успешно создана для товара {self.id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка генерации этикетки: {str(e)}", exc_info=True)
            return False

    def _generate_barcode_image(self):
        """Генерирует изображение штрих-кода в памяти"""
        barcode_str = str(self.barcode).strip().zfill(12)[:12]
        full_ean = barcode_str + self._calculate_ean13_checksum(barcode_str)

        try:
            # Создаем штрих-код в памяти
            ean = barcode.get_barcode_class('ean13')
            barcode_buffer = BytesIO()
            ean(full_ean, writer=ImageWriter()).write(barcode_buffer)
            barcode_buffer.seek(0)
            barcode_img = PILImage.open(barcode_buffer)

            # Масштабируем штрих-код до нужного размера
            barcode_img = barcode_img.resize((120, 100), PILImage.Resampling.LANCZOS)
            return barcode_img

        except Exception as e:
            logger.error(f"Ошибка генерации штрих-кода: {str(e)}")
            raise

    def _create_label_image(self, barcode_img):
        """Создает этикетку в памяти с улучшенной компоновкой"""
        try:
            # 1. Создаем холст (увеличиваем высоту для всех элементов)
            label_width, label_height = 120, 100
            label_img = PILImage.new("RGB", (label_width, label_height), "white")
            draw = ImageDraw.Draw(label_img)

            # 2. Настраиваем шрифты
            try:
                # Пробуем разные варианты шрифтов
                title_font = ImageFont.truetype("arial.ttf", 18)
                info_font = ImageFont.truetype("arial.ttf", 25)
                barcode_font = ImageFont.truetype("arial.ttf", 12)
            except (OSError, IOError):
                try:
                    # Для Linux систем
                    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
                    info_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
                    barcode_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
                except (OSError, IOError):
                    # Используем стандартный шрифт
                    title_font = ImageFont.load_default()
                    info_font = ImageFont.load_default()
                    barcode_font = ImageFont.load_default()

            # 3. Добавляем название товара (с переносом строк если длинное)
            y_offset = 10
            name_text = self.name[:50] + '...' if len(self.name) > 50 else self.name

            # Центрируем название
            bbox = draw.textbbox((0, 0), name_text, font=title_font)
            text_width = bbox[2] - bbox[0]
            x_center = (label_width - text_width) // 2

            draw.text((x_center, y_offset), name_text, fill="black", font=title_font)
            y_offset += 35

            # 4. Добавляем информацию о товаре
            info_lines = []

            # # Цена
            # if self.sale_price:
            #     info_lines.append(f"Цена: {self.sale_price:.2f} UZS")


            # # Размер
            # if self.size:
            #     info_lines.append(f"Размер: {self.size}")

            # # Единица измерения
            # info_lines.append(f"Единица: {self.get_unit_display()}")

            # # Категория
            # if self.category:
            #     info_lines.append(f"Категория: {self.category.name}")

            # Отображаем информацию
            # for line in info_lines:
            #     bbox = draw.textbbox((0, 0), line, font=info_font)
            #     text_width = bbox[2] - bbox[0]
            #     x_center = (label_width - text_width) // 2
            #     draw.text((x_center, y_offset), line, fill="black", font=info_font)
            #     y_offset += 25



            # 5. Добавляем штрих-код
            y_offset += 10  # Небольшой отступ
            barcode_width, barcode_height = barcode_img.size
            x_barcode = (label_width - barcode_width) // 2

            # Вставляем штрих-код
            label_img.paste(barcode_img, (x_barcode, y_offset))
            y_offset += barcode_height + 5

            # 6. Добавляем номер штрих-кода под изображением
            # barcode_text = str(self.barcode)
            # bbox = draw.textbbox((0, 0), barcode_text, font=barcode_font)
            # text_width = bbox[2] - bbox[0]
            # x_center = (label_width - text_width) // 2

            # draw.text((x_center, y_offset), barcode_text, fill="black", font=barcode_font)
            # y_offset += barcode_font.getsize(barcode_text)[1]

            # 7. Добавляем рамку
            # draw.rectangle([0, 0, label_width-1, label_height-1], outline="black", width=2)

            # 8. Сохраняем в bytes
            buffer = BytesIO()
            label_img.save(buffer, format="PNG", quality=95)
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Ошибка создания этикетки: {str(e)}", exc_info=True)
            raise

    def _calculate_ean13_checksum(self, digits):
        """Вычисляет контрольную цифру EAN-13"""
        weights = [1, 3] * 6
        total = sum(int(d) * w for d, w in zip(digits, weights))
        return str((10 - (total % 10)) % 10)

    def save(self, *args, **kwargs):
        """Переопределяем save для автоматической генерации этикетки"""
        is_new = self._state.adding
        update_fields = kwargs.get('update_fields')

        # Если обновляем только image_label — не генерируем заново
        if update_fields and update_fields == ['image_label']:
            super().save(*args, **kwargs)
            return

        # Сохраняем сначала, чтобы был self.id (для генерации label_filename)
        super().save(*args, **kwargs)

        # Поля, которые влияют на этикетку
        label_relevant_fields = ['name', 'barcode', 'sale_price', 'size']

        # Проверяем, изменились ли они (только если объект уже существовал)
        if not is_new:
            current = Product.objects.filter(pk=self.pk).values(*label_relevant_fields).first()
            if current:
                fields_changed = any(
                    str(getattr(self, f)) != str(current[f])
                    for f in label_relevant_fields
                    if getattr(self, f) is not None or current[f] is not None
                )
            else:
                fields_changed = False
        else:
            fields_changed = True  # новый товар — точно нужна этикетка

        # Генерируем этикетку, если это новый товар или поля изменились
        if is_new or fields_changed:
            self.generate_label()


class ProductAttribute(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='product_attributes',
        verbose_name="Товар"
    )
    attribute_value = models.ForeignKey(
        AttributeValue,
        on_delete=models.CASCADE,
        related_name='product_attributes',
        verbose_name="Значение атрибута"
    )

    class Meta:
        verbose_name = "Атрибут товара"
        verbose_name_plural = "Атрибуты товаров"
        unique_together = ('product', 'attribute_value')

    def __str__(self):
        return f"{self.product.name} - {self.attribute_value.value}"

class SizeChart(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Таблица размеров"
        verbose_name_plural = "Таблицы размеров"
        ordering = ['name']

    def __str__(self):
        return self.name



class ProductBatch(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='batches'
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Количество"
    )
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Цена закупки",
    )
    size = models.ForeignKey(
        SizeInfo,  # или как у тебя называется модель размера
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="Размер"
    )
    supplier = models.CharField(max_length=255, blank=True, null=True,  verbose_name="Поставщик")
    expiration_date = models.DateField(null=True, blank=True, verbose_name="Дата истечения")
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
        related_name='stock',
        verbose_name="Товар"
    )
    quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Количество"
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