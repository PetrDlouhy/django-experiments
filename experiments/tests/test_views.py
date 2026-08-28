from __future__ import absolute_import

from django.contrib.sessions.backends.db import SessionStore as DatabaseSession
from django.test import TestCase
from django.urls import reverse

from experiments import conf
from experiments.utils import WebUser

from mock import patch

OAUTH_STATE_KEY = 'oauth_state'
OAUTH_STATE = 'state-written-by-a-concurrent-request'


class ConfirmHumanViewTest(TestCase):
    def setUp(self):
        session = DatabaseSession()
        session['seeded'] = 'before'
        session.save()
        self.session_key = session.session_key
        self.client.cookies['sessionid'] = self.session_key
        self.url = reverse('experiment_confirm_human')

    def stored(self):
        return DatabaseSession(session_key=self.session_key)

    def test_get_is_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_post_marks_the_session_as_human(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertTrue(self.stored().get(conf.CONFIRM_HUMAN_SESSION_KEY))

    def test_leaves_untouched_keys_alone(self):
        self.client.post(self.url)
        self.assertEqual(self.stored().get('seeded'), 'before')

    def test_does_not_drop_a_concurrent_session_write(self):
        """A write landing while confirm_human replays counters must survive.

        confirm_human() can spend seconds replaying enrollments and goals to
        the counter store. A concurrent request writing to the same session in
        that window (an OAuth login storing its state, for example) used to be
        overwritten when this request's stale session snapshot was saved at the
        end of the request. The concurrent write is injected inside
        confirm_human(), which is exactly where such requests land.
        """
        original = WebUser.confirm_human

        def concurrent_write_then_confirm(user):
            concurrent = DatabaseSession(session_key=self.session_key)
            concurrent[OAUTH_STATE_KEY] = OAUTH_STATE
            concurrent.save()
            return original(user)

        with patch.object(WebUser, 'confirm_human', concurrent_write_then_confirm):
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 204)
        stored = self.stored()
        self.assertEqual(stored.get(OAUTH_STATE_KEY), OAUTH_STATE)
        self.assertTrue(stored.get(conf.CONFIRM_HUMAN_SESSION_KEY))

    def test_repeat_ping_makes_no_session_write(self):
        self.client.post(self.url)
        with patch.object(DatabaseSession, 'save') as save:
            self.client.post(self.url)
        save.assert_not_called()

    def test_without_a_session_cookie_it_still_answers(self):
        del self.client.cookies['sessionid']
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 204)
