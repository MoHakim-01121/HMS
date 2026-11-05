import os
import shutil
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from hw.models import Attachment, RoleDefinition, UserProfile
from hw.tests.factories import make_cl


class AttachmentDeleteTests(TestCase):
    def setUp(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=root)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(User.objects.create_user('desk', password='pw12345'))
        self.att = Attachment(cl=make_cl(), name='a.pdf', size=4)
        self.att.file.save('a.pdf', ContentFile(b'%PDF'))
        self.path = self.att.file.path

    def _delete(self):
        return self.client.post(f'/attachments/{self.att.pk}/delete/')

    def _login_with_permissions(self, slug, permissions):
        RoleDefinition.objects.create(slug=slug, label=slug, permissions=permissions)
        user = User.objects.create_user(slug, password='pw12345')
        UserProfile.objects.filter(user=user).update(role=slug)
        user.refresh_from_db()
        self.client.force_login(user)

    def test_cl_editor_can_upload_and_delete_cl_attachment(self):
        cl = make_cl()
        self._login_with_permissions('cl-editor-only', {'cl': ['edit']})

        response = self.client.post('/attachments/upload/', {
            'cl_id': cl.pk,
            'file': SimpleUploadedFile('proof.pdf', b'%PDF-1.4\nproof'),
        })

        self.assertEqual(response.status_code, 200)
        attachment = Attachment.objects.get(pk=response.json()['id'])
        self.assertEqual(attachment.cl_id, cl.pk)
        deleted = self.client.post(f'/attachments/{attachment.pk}/delete/')
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(Attachment.objects.filter(pk=attachment.pk).exists())

    def test_invoice_editor_cannot_manage_cl_attachment(self):
        cl = make_cl()
        self.att.cl = cl
        self.att.save()
        self._login_with_permissions('invoice-editor-only', {'invoice': ['edit']})

        upload = self.client.post('/attachments/upload/', {
            'cl_id': cl.pk,
            'file': SimpleUploadedFile('proof.pdf', b'%PDF-1.4\nproof'),
        })
        deleted = self.client.post(f'/attachments/{self.att.pk}/delete/')

        self.assertEqual(upload.status_code, 403)
        self.assertEqual(deleted.status_code, 403)
        self.assertTrue(Attachment.objects.filter(pk=self.att.pk).exists())

    def _upload_as_cl_editor(self, name, content):
        self._login_with_permissions('cl-uploader', {'cl': ['edit']})
        return self.client.post('/attachments/upload/', {
            'cl_id': make_cl().pk, 'file': SimpleUploadedFile(name, content),
        })

    def test_csv_upload_is_accepted(self):
        # libmagic reports a CSV as text/plain.
        resp = self._upload_as_cl_editor('rooms.csv', b'name,amount\nAli,100\nBudi,200\n')
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_jpeg_extension_is_accepted(self):
        jpeg = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00' + b'\x00' * 64
        resp = self._upload_as_cl_editor('photo.jpeg', jpeg)
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_mismatched_extension_is_refused_with_a_reason(self):
        resp = self._upload_as_cl_editor('proof.png', b'%PDF-1.4\nproof')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error'], 'The file extension does not match its content.')

    def test_removes_the_row_and_the_file(self):
        self.assertEqual(self._delete().status_code, 200)
        self.assertFalse(Attachment.objects.filter(pk=self.att.pk).exists())
        self.assertFalse(os.path.exists(self.path))

    def test_a_file_that_cannot_be_removed_is_logged_and_the_row_still_goes(self):
        with (mock.patch.object(FileSystemStorage, 'delete', side_effect=OSError('busy')),
              self.assertLogs('hw.views.attachment_views', level='ERROR')):
            resp = self._delete()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Attachment.objects.filter(pk=self.att.pk).exists())
