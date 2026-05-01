from django.contrib import admin,messages
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html
from urllib.parse import urlencode
from .models import Product,Collection,Customer,Order,OrderItem, ProductImage 

class Order_Item(admin.TabularInline):
    model = OrderItem 
    extra = 1
    autocomplete_fields = ['product']

class InventoryStatus(admin.SimpleListFilter):
    title = 'Inventory'
    parameter_name = 'inventory' 

    def lookups(self, request, model_admin):
        return [
            ('<10','Low')
        ]

    def queryset(self, request, queryset):
        if self.value() == '<10':
            return queryset.filter(inventory__lt=10)


class ProductImageAdmin(admin.TabularInline):
    model = ProductImage
    readonly_fields = ['thumbnail']
    extra = 1

    class Media:
        css = {
            'all': ['store/styles.css']
        }

    def thumbnail(self,instance):
        if instance.image:
            return format_html("<img src='{}' class='thumbnail'/>",instance.image.url,)
        return ''


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    autocomplete_fields = ['collection']
    prepopulated_fields = {
        'slug':['title']
    }
    actions = ['clear_inventory']
    inlines = [ProductImageAdmin]
    list_display = ['id','title','unit_price','Inventory_Status','collection_title']
    list_editable = ['title','unit_price']
    list_filter = ['collection','last_update',InventoryStatus]
    list_per_page = 10
    list_select_related = ['collection']
    search_fields = ['title']

    @admin.display(ordering='inventory')
    def Inventory_Status(self,product):
        if product.inventory < 10:
            return 'LOW - Less than 10 remaining'
        return 'OK'

    def collection_title(self,product):
        return product.collection.title

    @admin.action(description='Clear Inventory')
    def clear_inventory(self,request,queryset):
        updated_count = queryset.update(inventory = 0)
        self.message_user(
            request,
            f'{updated_count} products successfully updated',
            messages.SUCCESS
        )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    autocomplete_fields = ['customer']
    list_display = ['id','placed_at','customer_name','payment_status']
    list_editable=['payment_status']
    list_per_page = 10
    inlines = [Order_Item]

    def customer_name(self,order):
        return f"{order.customer.user.first_name} {order.customer.user.last_name}"

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['id','user_first_name','user_last_name','membership','orders']
    list_editable=['membership']
    list_per_page = 10
    search_fields = ['user__first_name__istartswith','user__last_name__istartswith',]

    @admin.display(ordering='orders_count')
    def orders(self, customer):
        url = (
            reverse('admin:store_order_changelist')
            + '?'
            + urlencode({'customer__id': str(customer.id)})
        )
        return format_html('<a href="{}">{}</a>', url, customer.orders_count)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            orders_count=Count('order')
        )
    
    @admin.display(ordering='user.first_name')
    def user_first_name(self,obj):
        return str(obj.user.first_name)
    
    @admin.display(ordering='user.last_name')
    def user_last_name(self,obj):
        return str(obj.user.last_name)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    autocomplete_fields = ['featured_product']
    list_display = ['title','products_count']
    search_fields = ['title']

    @admin.display(ordering='products_count')
    def products_count(self,collection):
        url = reverse('admin:store_product_changelist') + '?' + urlencode({
        "collection__id":str(collection.id)
        })
        return format_html('<a href="{}">{}</a>',url,collection.products_count)
    
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(products_count = Count('product'))


