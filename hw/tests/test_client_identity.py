"""Schema v2 F2a — satu perusahaan satu baris client, dan setiap client punya cabang pemilik."""
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from hw.models import Branch, Client
from hw.models.client import client_name_key


class NameKeyTest(TestCase):
    def test_normalises_case_spacing_punctuation_and_legal_form(self):
        self.assertEqual(client_name_key('PT. Safaar'), 'safaar')
        self.assertEqual(client_name_key('  SAFAAR  '), 'safaar')
        self.assertEqual(client_name_key('Asosiasi   Berpahala'), 'asosiasi berpahala')
        self.assertEqual(client_name_key('CV Nur-Sultan'), 'nur sultan')

    def test_name_made_only_of_a_legal_form_is_kept(self):
        self.assertEqual(client_name_key('PT'), 'pt')

    def test_save_fills_name_key_and_follows_rename(self):
        c = Client.objects.create(name='PT. Safaar')
        self.assertEqual(c.name_key, 'safaar')
        c.name = 'Gema Wisata'
        c.save(update_fields=['name'])
        c.refresh_from_db()
        self.assertEqual(c.name_key, 'gema wisata')

    def test_database_refuses_a_second_row_for_the_same_company(self):
        Client.objects.create(name='Safaar')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Client.objects.create(name='SAFAAR')

    def test_display_name_prefers_brand(self):
        self.assertEqual(Client(name='PT Maju Jaya', brand='Amanah Tour').display_name, 'Amanah Tour')
        self.assertEqual(Client(name='PT Maju Jaya').display_name, 'PT Maju Jaya')


class OwnerBranchTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', password='x')
        self.client.force_login(self.user)

    def test_defaults_to_surabaya(self):
        self.assertEqual(Client.objects.create(name='A').owner_branch_id, 'sby')

    def test_only_one_head_office(self):
        self.assertEqual(list(Branch.objects.filter(is_hq=True).values_list('code', flat=True)), ['pusat'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Branch.objects.filter(code='sby').update(is_hq=True)

    def test_form_saves_owner_branch(self):
        Branch.objects.filter(code='jkt').update(is_active=True)
        self.client.post(reverse('client_new'), {'name': 'Jakarta Tour', 'owner_branch': 'jkt', 'is_active': 'on'})
        self.assertEqual(Client.objects.get(name='Jakarta Tour').owner_branch_id, 'jkt')

    def test_form_rejects_inactive_branch(self):
        Branch.objects.filter(code='jkt').update(is_active=False)
        self.client.post(reverse('client_new'), {'name': 'Jakarta Tour', 'owner_branch': 'jkt', 'is_active': 'on'})
        self.assertFalse(Client.objects.filter(name='Jakarta Tour').exists())

    def test_form_rejects_duplicate_company_with_a_message(self):
        Client.objects.create(name='Safaar')
        self.client.post(reverse('client_new'), {'name': 'PT. SAFAAR', 'owner_branch': 'sby', 'is_active': 'on'})
        self.assertEqual(Client.objects.count(), 1)

    def test_form_rejects_unknown_branch(self):
        self.client.post(reverse('client_new'), {'name': 'X Tour', 'owner_branch': 'zzz', 'is_active': 'on'})
        self.assertFalse(Client.objects.filter(name='X Tour').exists())

    def test_edit_keeps_own_name(self):
        c = Client.objects.create(name='Safaar')
        self.client.post(reverse('client_edit', args=[c.pk]), {'name': 'Safaar', 'brand': 'Safaar Travel', 'owner_branch': 'sby', 'is_active': 'on'})
        c.refresh_from_db()
        self.assertEqual(c.brand, 'Safaar Travel')
