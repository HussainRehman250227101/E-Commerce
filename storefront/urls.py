from django.contrib import admin
from django.urls import path,include
from django.conf.urls.static import static
from django.conf import settings
# from debug_toolbar.toolbar import debug_toolbar_urls
from store.views import Ping


urlpatterns = [
    path('admin/', admin.site.urls),
    path('ping/', Ping.as_view()),
    path('playground/', include('playground.urls')),
    path('store/', include('store.urls')),
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.jwt')),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT)
