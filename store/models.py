from uuid import uuid4
from django.db import models
from django.core.validators import MinValueValidator,MaxValueValidator
from django.conf import settings
from store.validators import ProductImageSizeValidator


# PROMOTION MODEL
class Promotion(models.Model):
    description = models.CharField(max_length=255) 
    discount = models.FloatField()

    def __str__(self):
        return str(self.description)


# COLLECTION MODEL
class Collection(models.Model):
    title = models.CharField(max_length=255) 
    featured_product = models.ForeignKey('Product',on_delete=models.SET_NULL,null=True, related_name = 'product_collection',blank=True)


    class Meta:
        ordering = ['title']

    def __str__(self):
        return str(self.title)


# PRODUCT MODEL
class Product(models.Model):
    # FIELDS BELOW
    title = models.CharField(max_length=255) 
    slug = models.SlugField()
    description = models.TextField()
    unit_price = models.DecimalField(max_digits=6,decimal_places=2,validators=[MinValueValidator(0.01),MaxValueValidator(9999)]) 
    inventory = models.IntegerField(validators=[MinValueValidator(0)],default=0)
    last_update = models.DateTimeField(auto_now=True) 
    collection = models.ForeignKey(Collection, on_delete=models.PROTECT,related_name='products')
    rating = models.DecimalField( max_digits=2,decimal_places=1, validators=[MinValueValidator(0),MaxValueValidator(5)])
    promotions = models.ManyToManyField(Promotion, null=True, blank=True)

    class Meta:
        ordering = ['title','unit_price']

    def __str__(self):
        return str(self.title)

# PRODUCT IMAGE MODEL
class ProductImage(models.Model):
    product = models.ForeignKey(Product,on_delete=models.CASCADE,related_name='images')
    image = models.ImageField(upload_to='store/images', validators=[ProductImageSizeValidator])


# CUSTOMER MODEL
class Customer(models.Model):
    MEMBERSHIP_BRONZE = 'B'
    MEMBERSHIP_SILVER = 'S'
    MEMBERSHIP_GOLD = 'G'
    MEMBERSHIP_CHOICES = [
        (MEMBERSHIP_BRONZE,'Bronze'),
        (MEMBERSHIP_SILVER,'Silver'),
        (MEMBERSHIP_GOLD,'Gold'),
    ]
    # FIELDS BELOW
    phone = models.PositiveBigIntegerField()
    birth_date = models.DateField(null=True)
    membership = models.CharField(max_length=1,choices=MEMBERSHIP_CHOICES, default=MEMBERSHIP_BRONZE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    profile_image = models.ImageField(upload_to='images',null=True)

    class Meta:
        ordering = ['user__first_name','user__last_name']
        permissions = [
            ('view_history', 'can view history')
        ]

    def __str__(self):
        return str(f'{self.user.first_name} {self.user.last_name}')


# ORDER MODEL
class Order(models.Model):
    ORDER_STATUS_PENDING = 'P' 
    ORDER_STATUS_COMPLETE = 'C'
    ORDER_STATUS_FAILED = 'F'
    ORDER_STATUS = [
        (ORDER_STATUS_PENDING,'P'),
        (ORDER_STATUS_COMPLETE, 'C'),
        (ORDER_STATUS_FAILED , 'F'),
    ]
    # FILEDS BELOW
    placed_at = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(max_length=1,choices=ORDER_STATUS,default=ORDER_STATUS_PENDING)
    customer = models.ForeignKey(Customer,on_delete=models.PROTECT)

    def __str__(self):
        return str(self.customer.user.first_name + ' ' + self.customer.user.last_name) 


# ORDER ITEM MODEL
class OrderItem(models.Model):
    order = models.ForeignKey(Order,on_delete=models.PROTECT,related_name='items')
    product = models.ForeignKey(Product,on_delete=models.SET_NULL,null=True,related_name='orderItems')
    quantity = models.PositiveSmallIntegerField() 
    unit_price = models.DecimalField(max_digits=6,decimal_places=2)  

    def __str__(self):
        return str(self.product)


# ADDRESS MODEL
class Address(models.Model):
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=255)
    customer = models.ForeignKey(Customer,on_delete=models.CASCADE,)

    def __str__(self):
        return str(self.customer.user.first_name + ' ' + self.customer.user.last_name + f" '  '{self.street} ' ' {self.city} ")


# CART MODEL
class Cart(models.Model):
    # items = models.ForeignKey(OrderItem, on_delete=models.CASCADE)
    id = models.UUIDField(default=uuid4,primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True) 


# CART ITEM MODEL
class CartItem(models.Model):
    cart = models.ForeignKey(Cart,on_delete=models.CASCADE,related_name='items')
    product = models.ForeignKey(Product,on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])  

    class Meta:
        unique_together = [['cart','product']]


# REVIEW MODEL
class Review(models.Model):
    product = models.ForeignKey(Product,on_delete=models.CASCADE,related_name='reviews')
    name = models.CharField(max_length=255)
    description = models.TextField() 
    created_at = models.DateTimeField(auto_now_add=True) 

    