from django.db import models


class Company(models.TextChoices):
    KONOZ  = 'konoz',  'Konoz United'
    IJABAH = 'ijabah', 'Ijabah'


class InvoiceType(models.TextChoices):
    HOTEL = 'hotel', 'Hotel'
    VISA  = 'visa',  'Visa/Services'


class HotelCity(models.TextChoices):
    MAKKAH  = 'makkah',  'Makkah'
    MADINAH = 'madinah', 'Madinah'
