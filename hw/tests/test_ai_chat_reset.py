from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase


class AiChatResetTests(TestCase):
    """'New chat' in the Ask AI panel forgets the remembered exchanges."""

    def setUp(self):
        self.user = User.objects.create_superuser('rina', password='x')
        self.client.force_login(self.user)

    def ask(self, message):
        with mock.patch('hw.views.ai_views.get_chat_reply', return_value='ok') as reply:
            self.client.post('/ai/chat/', {'message': message}, content_type='application/json')
        return reply.call_args.kwargs['history']

    def test_reset_clears_history(self):
        self.ask('overdue invoices')
        self.assertEqual(len(self.client.session['ai_history']), 2)

        resp = self.client.post('/ai/chat/reset/')
        self.assertEqual(resp.json(), {'ok': True})
        self.assertNotIn('ai_history', self.client.session)
        # The next question goes out with no earlier context.
        self.assertEqual(self.ask('check-ins this week'), [])

    def test_reset_without_history_is_fine(self):
        self.assertEqual(self.client.post('/ai/chat/reset/').status_code, 200)

    def test_reset_needs_post_and_login(self):
        self.assertEqual(self.client.get('/ai/chat/reset/').status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post('/ai/chat/reset/').status_code, 302)
