from django.urls import path

from .views import ShoppingAssistantChatView

urlpatterns = [
    path("chat/", ShoppingAssistantChatView.as_view(), name="shopping-assistant-chat"),
]
