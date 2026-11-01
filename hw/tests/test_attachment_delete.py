import os
import shutil
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import TestCase, override_settings

from hw.models import Attachment
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
