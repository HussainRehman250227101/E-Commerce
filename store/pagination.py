from rest_framework.pagination import PageNumberPagination 

class ProductPagnation(PageNumberPagination):
    page_size = 10