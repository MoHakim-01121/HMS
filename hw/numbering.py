"""Generic sequential number generator.

All models that produce prefixed, zero-padded sequential IDs (INV-001,
CL-003, PAY-0001, etc.) share the same pattern: atomic select-for-update,
filter by prefix, parse the trailing digits, return max+1.

This module replaces six copy-pasted ``generate_number`` classmethods
with a single reusable function.
"""
import re

from django.db import transaction


def generate_sequential_number(model, prefix, field=None, padding=3, extra_filter=None):
    """Return the next sequential ``{prefix}-{NNN}`` string for *model*.

    Parameters
    ----------
    model : django.db.models.Model
        The Django model class to query.
    prefix : str
        The prefix including the dash (e.g. ``'CL-'``, ``'INV'``).
        A trailing dash is appended automatically if missing.
    field : str, optional
        The ``CharField`` name to search.  Defaults to
        ``<model_name>_number``.
    padding : int, optional
        Zero-pad width (default ``3`` → ``001``).
    extra_filter : dict, optional
        Extra ``filter()`` kwargs (e.g. ``{'invoice_type': 'hotel'}``).

    Returns
    -------
    str
        The next number, e.g. ``'CL-004'``.
    """
    if not prefix.endswith('-'):
        prefix = f'{prefix}-'

    if field is None:
        field = f'{model._meta.model_name}_number'

    filter_kwargs = {f'{field}__startswith': prefix}
    if extra_filter:
        filter_kwargs.update(extra_filter)

    with transaction.atomic():
        nums = []
        for num_str in (
            model.objects
            .select_for_update()
            .filter(**filter_kwargs)
            .values_list(field, flat=True)
        ):
            match = re.search(r'(\d+)$', str(num_str))
            if match:
                try:
                    nums.append(int(match.group(1)))
                except ValueError:
                    pass

    next_num = (max(nums) + 1) if nums else 1
    return f'{prefix}{next_num:0{padding}d}'
