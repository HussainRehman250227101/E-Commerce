from django.urls import path 
from debug_toolbar.toolbar import debug_toolbar_urls
from . import views

urlpatterns = [
    path('home/', views.hello_world,name='home')
]+ debug_toolbar_urls()
