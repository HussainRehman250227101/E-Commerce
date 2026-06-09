from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer,UserSerializer as BaseUserSerializer

from rest_framework import serializers


class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        fields = ['username','password','email','first_name',"last_name"]


class UserSerializer(BaseUserSerializer):
    is_staff = serializers.BooleanField(read_only=True)
    class Meta(BaseUserSerializer.Meta):
        fields = ['id','username','email','first_name','last_name','is_staff']