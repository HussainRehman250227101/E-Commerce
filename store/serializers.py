from decimal import Decimal,ROUND_HALF_UP
from operator import truediv
from typing import Required
from rest_framework import serializers
from .models import *

# COLLECTION SERIALIZER
class CollectionSerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField(read_only=True) 
    class Meta:
        model = Collection
        fields = ['id','title','products_count']
    
    def get_products_count(self,collection):
        return collection.products.count()


# PRODUCT IMAGE SERIALIZER
class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id','image']

    def create(self, validated_data):
        product_id = self.context['product_id']
        return ProductImage.objects.create(product_id = product_id,**validated_data)


# PRODUCT SERIALIZER
class ProductSerializer(serializers.ModelSerializer):
    collection = serializers.PrimaryKeyRelatedField(
        queryset = Collection.objects.all()
    )
    price_with_tax = serializers.SerializerMethodField() 
    images = ProductImageSerializer(many=True,read_only=True)
    featured_product = serializers.BooleanField(
    source="is_featured",
    read_only=True
    )

    class Meta:
        model = Product 
        fields = ['id','title','images','description','unit_price','price_with_tax','rating','inventory','featured_product','collection','promotions']
        read_only_fields = ['id','inventory','promotions']

    def get_price_with_tax(self,product):
        return (product.unit_price * Decimal("1.1")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    


# REVIEW SERIALIZER
class ReviewSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    image = serializers.ImageField(source='name.profile_image',read_only=True)
    class Meta:
        model = Review
        fields = ['id','name','image','rating','description','created_at'] 
        read_only_fields = ['id','name','created_at']

    def get_name(self, obj):
        return obj.name.user.first_name+" "+obj.name.user.last_name
    
   

    def create(self, validated_data):
        product_id = self.context['product_id']
        return Review.objects.create(product_id=product_id,**validated_data)


# SIMPLE PRODUCT SERIALIZER
class SimpleProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True,read_only=True)
    featured_product = serializers.SerializerMethodField(read_only=True)
    class Meta:
        model = Product
        fields = ['id','title','unit_price','rating','featured_product','images']
        read_only_fields = ['rating']

    def get_featured_product(sefl, product):
        return Collection.objects.filter(featured_product_id = product.id).exists() 


# SIMPLE CART ITEM SERIALIZER
class SimpleCartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True)
    product = serializers.SerializerMethodField(read_only=True)
    total_price = serializers.SerializerMethodField(read_only=True)
    

    class Meta:
        model = CartItem
        fields = ['id','product','quantity','total_price','product_id']

    def create(self, validated_data):
        cart_id = self.context['cart_id']
        product_id = validated_data.get('product_id')
        quantity = validated_data.get('quantity')

        cartItem,created = CartItem.objects.get_or_create(
            cart_id = cart_id,
            product_id = product_id,
            defaults={'quantity':quantity}
        )
        if not created:
            cartItem.quantity += quantity
            cartItem.save()
        return cartItem

    def validate_product_id(self,value):
        if not Product.objects.filter(pk=value).exists():
            raise serializers.ValidationError('product does not exist') 
        return value
    
    def get_total_price(self,cartItem):
        return cartItem.product.unit_price * Decimal(cartItem.quantity)
    
    def get_product(self,cartItem):
        return SimpleProductSerializer(cartItem.product).data


# CART ITEM SERIALIZER
class CartItemSerializer(serializers.ModelSerializer):
    total_price = serializers.SerializerMethodField()
    product = SimpleProductSerializer()

    class Meta:
        model = CartItem
        fields = ['id','product','quantity','total_price']

    def get_total_price(self,cartItem):
        return cartItem.product.unit_price * Decimal(cartItem.quantity)

# CART SERIALIZER
class CartSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    items = CartItemSerializer(many=True,read_only=True)
    total_price = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Cart
        fields = ['id','items','total_price'] 

    def get_total_price(self,obj):
        return sum([item.product.unit_price * Decimal(item.quantity) for item in obj.items.all()])


# ADMIN CUSTOMER SERIALIZER
class AdminCustomerSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField()
    class Meta:
        model = Customer
        fields = ['id','user_id','phone','birth_date','membership']


# CUSTOMER SERIALIZER
class CustomerSerializer(serializers.ModelSerializer):
    membership = serializers.CharField(max_length = 1,read_only= True)
    class Meta:
        model = Customer
        fields = ['phone','birth_date','membership','profile_image']


# CREATE ORDER SERIALIZER
class CreateOrderSerializer(serializers.Serializer):
    cart_id = serializers.UUIDField()

    def validate_cart_id(self,cart_id):
        if not Cart.objects.filter(pk = cart_id).exists():
           raise serializers.ValidationError('no cart exists')
        elif CartItem.objects.filter(cart = cart_id).count() == 0:
            raise serializers.ValidationError('no items exist')
        return cart_id

    def save(self, **kwargs):
       user_id = self.context['user_id']
       cart_id = self.validated_data['cart_id']
       cartItems = CartItem.objects.filter(cart = cart_id)
       (customer,created) = Customer.objects.get_or_create(user__id = user_id)
        
       order = Order.objects.create(customer = customer)
       items = [OrderItem(
                order = order, 
                product = item.product,
                quantity = item.quantity,
                unit_price = item.product.unit_price) for item in cartItems]
                
       OrderItem.objects.bulk_create(items)
       Cart.objects.get(id = cart_id).delete()
       return order    


# ORDER ITEM SERIALIZER
class OrderitemSerializer(serializers.ModelSerializer):
    product = SimpleProductSerializer()
    class Meta:
        model = OrderItem
        fields = ['id','product','quantity','unit_price']


# ORDER SERIALIZER
class OrderSerializer(serializers.ModelSerializer):
    items = OrderitemSerializer(many=True)
    class Meta:
        model = Order
        fields = ['id','customer','payment_status','placed_at','items'] 


# UPDATE ORDER SERIALIZER
class UpdateOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['payment_status'] 

