"""MealPlan — controlled master for board type (Master Architecture v2.0 §10).

Room.meals stays as free text (legacy data, hotel-specific notes like
"BB + late checkout"); meal_plan is the optional structured link for
reporting/filtering, same additive pattern as RoomType.occupancy/view.
"""
from django.db import models


class MealPlan(models.Model):
    code       = models.CharField(max_length=10, primary_key=True)
    name       = models.CharField(max_length=100)
    is_active  = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Meal Plan'
        verbose_name_plural = 'Meal Plans'

    def __str__(self):
        return f'{self.code} — {self.name}'
