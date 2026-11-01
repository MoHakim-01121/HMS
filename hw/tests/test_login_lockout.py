"""The login lock: a user's failures lock that user on that address, never
everyone behind the same proxy or office network."""
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase

from hw.client_ip import client_ip


def fail_login(username, *, remote='127.0.0.1', forwarded='203.0.113.7'):
    return Client(REMOTE_ADDR=remote, HTTP_X_FORWARDED_FOR=forwarded).post(
        '/login/', {'username': username, 'password': 'nope'})


class LockoutScopeTests(TestCase):
    def setUp(self):
        User.objects.create_user('rina', password='umrah2026')

    def _sign_in(self, forwarded):
        return Client(REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_FOR=forwarded).post(
            '/login/', {'username': 'rina', 'password': 'umrah2026'})

    def test_other_usernames_failing_on_one_address_do_not_lock_a_colleague(self):
        for i in range(5):
            fail_login(f'typo{i}')
        resp = self._sign_in('203.0.113.7')
        self.assertRedirects(resp, '/dashboard/?logged_in=1', fetch_redirect_response=False)

    def test_failures_from_another_address_do_not_lock_the_real_user(self):
        for _ in range(5):
            fail_login('rina', forwarded='198.51.100.9')
        resp = self._sign_in('203.0.113.7')
        self.assertRedirects(resp, '/dashboard/?logged_in=1', fetch_redirect_response=False)

    def test_a_user_failing_five_times_on_one_address_is_locked_there(self):
        for _ in range(5):
            fail_login('rina')
        resp = self._sign_in('203.0.113.7')
        self.assertRedirects(resp, '/login/?locked=1', fetch_redirect_response=False)

    def test_one_address_is_stopped_after_too_many_sign_in_posts(self):
        # Frozen clock: the rate window must not roll over during the loop.
        with mock.patch('time.time', return_value=1_800_000_000.0):
            statuses = [fail_login(f'spray{i}').status_code for i in range(31)]
        self.assertEqual(statuses[:30], [200] * 30)
        self.assertEqual(statuses[30], 403)


class ClientIpTests(TestCase):
    def _ip(self, remote, **headers):
        return client_ip(RequestFactory().get('/', REMOTE_ADDR=remote, **headers))

    def test_behind_a_local_proxy_takes_the_address_the_proxy_appended(self):
        self.assertEqual(
            self._ip('127.0.0.1', HTTP_X_FORWARDED_FOR='1.1.1.1, 203.0.113.7'), '203.0.113.7')

    def test_behind_a_local_proxy_accepts_x_real_ip(self):
        self.assertEqual(self._ip('10.0.0.2', HTTP_X_REAL_IP='203.0.113.7'), '203.0.113.7')

    def test_a_public_peer_cannot_forge_its_address(self):
        self.assertEqual(self._ip('8.8.8.8', HTTP_X_FORWARDED_FOR='1.1.1.1'), '8.8.8.8')

    def test_garbage_in_the_header_falls_back_to_the_peer(self):
        self.assertEqual(self._ip('127.0.0.1', HTTP_X_FORWARDED_FOR='not-an-ip'), '127.0.0.1')
