from django.urls import path 
from rest_framework_nested import routers
from. import views

router = routers.DefaultRouter()
router.register('products', views.ProductViewSet)
router.register('collections', views.CollectionViewSet) 
router.register('cart', views.CartViewSet) 
router.register('customers', views.CustomerViewSet) 
router.register('orders', views.OrderViewSet,basename='orders') 

products_router = routers.NestedDefaultRouter(router,'products',lookup='product')
products_router.register('reviews',views.ReviewViewSet,basename='products')
products_router.register('images',views.ProductImageViewSet,basename='product-image')

cart_router = routers.NestedDefaultRouter(router,'cart',lookup='cart')
cart_router.register('items',views.CartItemViewSet,basename='cart-items')

urlpatterns = router.urls + products_router.urls + cart_router.urls


# urlpatterns = [
#     path('products/',views.products_list),
#     path('products/<int:pk>/',views.product_detail),
#     path('collections/',views.collections_list),
#     path('collections/<int:pk>/',views.collection_detail),
# ]
