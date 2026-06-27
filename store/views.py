from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Exists, OuterRef

from rest_framework.decorators import APIView, action
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.filters import SearchFilter,OrderingFilter
from rest_framework.mixins import CreateModelMixin,RetrieveModelMixin,DestroyModelMixin 
from rest_framework.viewsets import GenericViewSet
from rest_framework.permissions import IsAdminUser,IsAuthenticated,AllowAny
from store.permissions import CanViewHistory, IsAdminOrReadOnly   

from .models import Cart, Order, Product,Collection, ProductImage,Review,CartItem,Customer
from .pagination import ProductPagnation
from .filters import ProductFilter
from .serializers import AdminCustomerSerializer, CartSerializer, CreateOrderSerializer, CustomerSerializer, OrderSerializer, ProductImageSerializer, ProductSerializer,CollectionSerializer,ReviewSerializer,CartItemSerializer, SimpleCartItemSerializer, UpdateOrderSerializer



# PRODUCT VIEW SET
class ProductViewSet(ModelViewSet):
    queryset = Product.objects.annotate(is_featured=Exists(Collection.objects.filter(featured_product_id=OuterRef("pk")))).select_related("collection").prefetch_related("images",'promotions')
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend,SearchFilter,OrderingFilter]
    pagination_class = ProductPagnation
    filterset_class = ProductFilter
    search_fields = ['title','description']
    ordering_fields = ['unit_price']
    permission_classes = [IsAdminOrReadOnly]

    def destroy(self, request, *args, **kwargs):
        product =  self.get_object() 
        if product.objects.prefetch_related('orderItems').count() > 0 :
            return Response({"error":"this product cannot be deleted as it has order items associated to it"})
        return super().destroy(request, *args, **kwargs)   



# COLLECTION VIEW SET
class CollectionViewSet(ModelViewSet):
    queryset = Collection.objects.all() 
    serializer_class = CollectionSerializer 
    permission_classes = [IsAdminOrReadOnly]

    def destroy(self, request, *args, **kwargs):
        collection =  self.get_object() 
        if collection.products.count() > 0 :
            return Response({"error":"this collection cannot be deleted as it has products associated to it"})
        return super().destroy(request, *args, **kwargs) 

# REVIEW VIEW SET 
class ReviewViewSet(ModelViewSet):
    serializer_class = ReviewSerializer 

    def get_queryset(self):
        return Review.objects.filter(product_id = self.kwargs['product_pk'])

    def get_serializer_context(self):
        return {"product_id":self.kwargs['product_pk']}

# CART VIEW SET
class CartViewSet(CreateModelMixin,RetrieveModelMixin,DestroyModelMixin,GenericViewSet):
    queryset = Cart.objects.prefetch_related('items__product').all()
    serializer_class = CartSerializer

# CART ITEM VIEW SET
class CartItemViewSet(ModelViewSet):
    http_method_names = ['get','post','patch','delete','head','options']

    def get_queryset(self):
        return CartItem.objects.filter(cart__id=self.kwargs['cart_pk']) 
    
    def get_serializer_class(self):
        if self.request.method in ['POST','PATCH']:
            return SimpleCartItemSerializer
        return CartItemSerializer 
    
    def get_serializer_context(self):
        return {'cart_id': self.kwargs.get('cart_pk')} 
    
class CustomerViewSet(ModelViewSet):
    queryset = Customer.objects.all()

    def get_permissions(self):
        if  self.action in ['create', 'me']:
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def get_serializer_class(self):
        if self.action in ['me', 'create'] :
            return CustomerSerializer
        return AdminCustomerSerializer

    @action(detail=True,permission_classes=[CanViewHistory])
    def history(self,request,pk):
        return Response('ok')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False,methods=['GET','PUT'],permission_classes=[IsAuthenticated])
    def me(self,request):
        customer = get_object_or_404(Customer,user=request.user)

        if request.method == 'GET':
            serializer = CustomerSerializer(customer)
            return Response(serializer.data)
        elif request.method == 'PUT':
            serializer  = CustomerSerializer(customer,data = request.data)
            serializer.is_valid(raise_exception = True)
            serializer.save()
        return Response(serializer.data) 

class OrderViewSet(ModelViewSet):
    http_method_names=['get','post','patch','delete']
    def get_permissions(self):
        if self.request.method in ['GET','POST']:
            return [IsAuthenticated()]
        elif self.request.method in ['PATCH','DELETE']:
            return [IsAdminUser()]
        return [IsAdminUser()]

    def get_queryset(self):
        user = self.request.user
        customer = Customer.objects.get(user = user)
        if self.request.user.is_staff:
            return Order.objects.all()
        return Order.objects.filter(customer = customer)

    def get_serializer_class(self):
        if self.request.method =='POST':
            return CreateOrderSerializer
        elif self.request.method =='PATCH':
            return UpdateOrderSerializer
        return OrderSerializer

    def create(self, request, *args, **kwargs):
        serializer = CreateOrderSerializer(data= request.data,context = {'user_id':self.request.user.id})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        serializer = OrderSerializer(order)
        return Response(serializer.data)

class ProductImageViewSet(ModelViewSet):

    def get_queryset(self):
        return ProductImage.objects.filter(product = self.kwargs['product_pk'])

    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminUser]

    def get_serializer_context(self):
        return {'product_id':self.kwargs['product_pk']}