from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from store.models import Product 
from tags.models import TaggedItem,Tag 
from store.admin import ProductAdmin, ProductImageAdmin 
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "usable_password","password1", "password2","email","first_name","last_name"),
            },
        ),
    )


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ['label']

class ProductTags(GenericTabularInline):
    autocomplete_fields = ['tag']
    model = TaggedItem 
    extra = 0

    def __str__(self):
        return str(self.tag.label)

class CustomProductAdmin(ProductAdmin):
    inlines = [ProductTags,ProductImageAdmin]
     
admin.site.unregister(Product)
admin.site.register(Product,CustomProductAdmin)