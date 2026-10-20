from django.contrib.auth.models import User
from django.test import TestCase


class LoginPageTests(TestCase):
    def setUp(self):
        User.objects.create_user('rina', password='umrah2026')

    def test_empty_page(self):
        resp = self.client.get('/login/')
        self.assertContains(resp, '<h1>Sign in</h1>', html=True)
        self.assertNotContains(resp, 'Wrong username or password')

    def test_wrong_password_counts_down_attempts(self):
        resp = self.client.post('/login/', {'username': 'rina', 'password': 'nope'})
        self.assertContains(resp, 'Wrong username or password')
        self.assertContains(resp, '4 attempts left before the account locks for 1 hour.')
        # The username is kept, the password is not.
        self.assertContains(resp, 'value="rina"')

        resp = self.client.post('/login/', {'username': 'rina', 'password': 'nope'})
        self.assertContains(resp, '3 attempts left')

    def test_fifth_failure_locks(self):
        for _ in range(4):
            self.client.post('/login/', {'username': 'rina', 'password': 'nope'})
        resp = self.client.post('/login/', {'username': 'rina', 'password': 'nope'})
        self.assertRedirects(resp, '/login/?locked=1', fetch_redirect_response=False)
        resp = self.client.get('/login/?locked=1')
        self.assertContains(resp, 'Account locked for 1 hour')

    def test_signed_out_notice(self):
        resp = self.client.get('/login/?logged_out=1')
        self.assertContains(resp, 'You have signed out')

    def test_success_redirects_to_dashboard(self):
        resp = self.client.post('/login/', {'username': 'rina', 'password': 'umrah2026', 'remember': '1'})
        self.assertRedirects(resp, '/dashboard/?logged_in=1', fetch_redirect_response=False)
