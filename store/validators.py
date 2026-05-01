from django.core.exceptions import ValidationError

def ProductImageSizeValidator(file):
    max_image_size = 5000

    if file.size > max_image_size *1024:
        raise ValidationError(f'Image sixe must be less than {max_image_size} KB.')
