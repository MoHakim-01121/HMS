from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hw', '0014_activitylog_changes'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='cl',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cl_payments',
                to='hw.confirmationletter',
            ),
        ),
        # Backfill: link existing payments to CLs via linked_number
        migrations.RunSQL(
            sql="""
                UPDATE invoices_payment
                SET cl_id = (
                    SELECT id FROM invoices_confirmationletter
                    WHERE confirmation_number = invoices_payment.linked_number
                    LIMIT 1
                )
                WHERE linked_number != ''
                  AND cl_id IS NULL
                  AND EXISTS (
                      SELECT 1 FROM invoices_confirmationletter
                      WHERE confirmation_number = invoices_payment.linked_number
                  );
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
