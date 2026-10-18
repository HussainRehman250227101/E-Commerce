from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Count, Exists, OuterRef

from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.filters import SearchFilter,OrderingFilter
from rest_framework.mixins import CreateModelMixin,RetrieveModelMixin,DestroyModelMixin 
from rest_framework.viewsets import GenericViewSet
from rest_framework.permissions import IsAdminUser,IsAuthenticated
from store.permissions import CanViewHistory, IsAdminOrReadOnly   

from .models import Cart, Order, Product,Collection, ProductImage,Review,CartItem,Customer, OrderItem
from .pagination import ProductPagnation
from .filters import ProductFilter
from .recommender import FEATURE_WEIGHTS, METHOD_SUMMARY, get_content_index
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

    @action(detail=True, methods=['get'])
    def similar(self, request, pk=None):
        """Products whose content is closest to this product."""
        product = self.get_object()
        limit = _recommendation_limit(request)
        index = get_content_index()
        if product.id not in index.by_id:
            index = get_content_index(force=True)
        ranked = index.similar_to(product.id, limit=limit)
        return Response(_recommendation_payload([product.id], ranked, request))

    @action(detail=False, methods=['get'])
    def recommended(self, request):
        """Products closest to pages opened, searches, the cart, and past orders.

        Guests send visited product ids, recent search text, and cart ids.
        Signed-in shoppers also contribute the products they have ordered.
        With no activity, the response falls back to highly rated products.
        """
        limit = _recommendation_limit(request)
        cart_ids = _parse_product_ids(request.query_params.get('product_ids'))
        visit_ids = _parse_product_ids(request.query_params.get('visited_ids'))
        search_text = (request.query_params.get('search') or '').strip()[:300]
        order_ids = []
        if request.user.is_authenticated:
            order_ids = list(
                OrderItem.objects.filter(
                    order__customer__user=request.user,
                ).exclude(product_id__isnull=True).values_list('product_id', flat=True).distinct()
            )

        if not cart_ids and not visit_ids and not order_ids and not search_text:
            return Response(_cold_start_payload(limit, request))

        index = get_content_index()
        ranked = index.recommend_from_activity(
            cart_ids=cart_ids,
            order_ids=order_ids,
            visit_ids=visit_ids,
            search_text=search_text,
            limit=limit,
        )
        known_seeds = [
            product_id for product_id in dict.fromkeys([*visit_ids, *cart_ids, *order_ids])
            if product_id in index.by_id
        ]
        if not ranked:
            return Response(_cold_start_payload(limit, request))
        return Response(_recommendation_payload(
            known_seeds,
            ranked,
            request,
            summary=_activity_summary(visit_ids, cart_ids, order_ids, search_text),
        ))


def _recommendation_limit(request, default=8):
    raw = request.query_params.get('limit', default)
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = default
    return max(1, min(limit, 20))


def _parse_product_ids(raw):
    if not raw:
        return []
    parsed = []
    seen = set()
    for part in str(raw).split(','):
        part = part.strip()
        if not part.isdigit():
            continue
        product_id = int(part)
        if product_id in seen:
            continue
        seen.add(product_id)
        parsed.append(product_id)
        if len(parsed) == 50:
            break
    return parsed


def _catalog_queryset():
    return Product.objects.annotate(
        is_featured=Exists(Collection.objects.filter(featured_product_id=OuterRef('pk')))
    ).select_related('collection').prefetch_related('images', 'promotions')


def _recommendation_payload(seed_ids, ranked, request, summary=None):
    return {
        'strategy': 'content_based',
        'summary': summary or METHOD_SUMMARY,
        'feature_weights': FEATURE_WEIGHTS,
        'seed_product_ids': seed_ids,
        'results': _serialize_ranked(ranked, request),
    }


def _activity_summary(visit_ids, cart_ids, order_ids, search_text):
    pieces = []
    if visit_ids:
        pieces.append('products you opened')
    if search_text:
        pieces.append(f'your search "{search_text}"')
    if cart_ids:
        pieces.append('your cart')
    if order_ids:
        pieces.append('your orders')
    joined = ', '.join(pieces) if pieces else 'your recent activity'
    return (
        'Content-based filtering from ' + joined + '. '
        'Matches use the title, description, collection, price, and rating.'
    )


def _serialize_ranked(ranked, request):
    product_ids = [item.product_id for item in ranked]
    products = {
        product.id: product
        for product in _catalog_queryset().filter(id__in=product_ids)
    }
    results = []
    for item in ranked:
        product = products.get(item.product_id)
        if product is None:
            continue
        results.append({
            'similarity': round(item.similarity, 4),
            'reasons': item.reasons,
            'matched_terms': item.matched_terms,
            'anchor_product_id': item.anchor_product_id,
            'anchor_title': item.anchor_title,
            'parts': item.parts,
            'product': ProductSerializer(product, context={'request': request}).data,
        })
    return results


def _cold_start_payload(limit, request):
    products = list(
        _catalog_queryset().filter(inventory__gt=0).order_by('-rating', 'title')[:limit]
    )
    if not products:
        products = list(_catalog_queryset().order_by('-rating', 'title')[:limit])
    return {
        'strategy': 'cold_start',
        'summary': (
            'No visits, searches, cart items, or orders yet, so these are the highest-rated '
            'products. Content-based filtering starts once you search, open a product, or add one to the cart.'
        ),
        'feature_weights': FEATURE_WEIGHTS,
        'seed_product_ids': [],
        'results': [
            {
                'similarity': None,
                'reasons': ['Highly rated, shown because there is no shopping history yet'],
                'matched_terms': [],
                'anchor_product_id': None,
                'anchor_title': None,
                'parts': {},
                'product': ProductSerializer(product, context={'request': request}).data,
            }
            for product in products
        ],
    }



# COLLECTION VIEW SET
class CollectionViewSet(ModelViewSet):
    queryset = Collection.objects.annotate(products_count=Count("products")) 
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