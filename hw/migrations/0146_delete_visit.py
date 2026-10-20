from django.db import migrations


class Migration(migrations.Migration):
    """The Visit feature is gone for good (its UI went in 5f87290): drop its
    tables. Photo files under media/visits/ are not touched here; remove that
    folder on the server by hand."""

    dependencies = [
        ('hw', '0145_expense_approval_flow'),
    ]

    operations = [
        migrations.DeleteModel(name='VisitPhoto'),
        migrations.DeleteModel(name='Visit'),
    ]
