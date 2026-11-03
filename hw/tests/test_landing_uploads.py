import shutil
import tempfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from hw.models import Pricelist, TeamMember
from hw.views.landing_views import LANDING_UPLOAD_MAX_SIZE, _clean_team_photo, _pricelist_error


class LandingUploadTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)
        self.user = User.objects.create_superuser('landing-admin', 'admin@example.test', 'pw12345')
        self.client.force_login(self.user)

    def _png(self):
        from PIL import Image

        image = Image.new('RGB', (2, 2), color='red')
        data = BytesIO()
        image.save(data, format='PNG')
        return data.getvalue()

    def test_team_photo_rejects_non_image_content(self):
        upload = SimpleUploadedFile('photo.jpg', b'<script>alert(1)</script>', content_type='image/jpeg')
        response = self.client.post('/manage-landing/team/new/', {
            'name': 'Test member', 'photo': upload,
        }, HTTP_X_INERTIA='true')

        self.assertIn('photo', response.json()['props']['errors'])
        self.assertFalse(TeamMember.objects.exists())

    def test_team_photo_rejects_oversized_upload(self):
        upload = SimpleUploadedFile('photo.jpg', b'x' * (LANDING_UPLOAD_MAX_SIZE + 1))

        cleaned, error = _clean_team_photo(upload)

        self.assertIsNone(cleaned)
        self.assertEqual(error, 'Photo is too large (max 10 MB).')

    def test_team_photo_is_reencoded_as_jpeg(self):
        upload = SimpleUploadedFile('photo.png', self._png(), content_type='image/png')
        response = self.client.post('/manage-landing/team/new/', {
            'name': 'Test member', 'photo': upload,
        }, HTTP_X_INERTIA='true')

        self.assertEqual(response.status_code, 302)
        member = TeamMember.objects.get(name='Test member')
        self.assertTrue(member.photo.name.endswith('.jpg'))
        from PIL import Image
        with Image.open(member.photo.path) as stored:
            self.assertEqual(stored.format, 'JPEG')

    def test_pricelist_rejects_spoofed_pdf(self):
        upload = SimpleUploadedFile('prices.pdf', b'<html>not a PDF</html>', content_type='application/pdf')
        response = self.client.post('/manage-landing/pricelist/new/', {
            'title': 'Test price list', 'file': upload,
        }, HTTP_X_INERTIA='true')

        self.assertIn('file', response.json()['props']['errors'])
        self.assertFalse(Pricelist.objects.exists())

    def test_pricelist_rejects_oversized_file(self):
        upload = SimpleUploadedFile(
            'prices.pdf', b'%PDF-' + b'x' * LANDING_UPLOAD_MAX_SIZE,
            content_type='application/pdf',
        )

        self.assertEqual(_pricelist_error(upload), 'File is too large (max 10 MB).')
