import django_rq
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.test import TestCase

from dcim.models import Site
from extras.choices import *
from extras.context_managers import WebRequestContext
from extras.models import ObjectChange, Webhook


class WebRequestContextTestCase(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='jacob',
            email='jacob@example.com',
            password='top_secret'
        )

        site_ct = ContentType.objects.get_for_model(Site)
        DUMMY_URL = "http://localhost/"
        DUMMY_SECRET = "LOOKATMEIMASECRETSTRING"

        webhooks = Webhook.objects.bulk_create((
            Webhook(name='Site Create Webhook', type_create=True, payload_url=DUMMY_URL, secret=DUMMY_SECRET),
        ))
        for webhook in webhooks:
            webhook.content_types.set([site_ct])

        self.queue = django_rq.get_queue('default')
        self.queue.empty()  # Begin each test with an empty queue

    def test_user_object_type_error(self):

        with self.assertRaises(TypeError):
            with WebRequestContext("a string is not a user object"):
                pass

    def test_request_object_type_error(self):

        class NotARequest:
            pass

        with self.assertRaises(TypeError):
            with WebRequestContext(self.user, NotARequest()):
                pass

    def test_change_log_created(self):

        with WebRequestContext(self.user):
            site = Site(name='Test Site 1')
            site.save()

        site = Site.objects.get(name='Test Site 1')
        oc_list = ObjectChange.objects.filter(
            changed_object_type=ContentType.objects.get_for_model(Site),
            changed_object_id=site.pk
        ).order_by('pk')
        self.assertEqual(len(oc_list), 1)
        self.assertEqual(oc_list[0].changed_object, site)
        self.assertEqual(oc_list[0].action, ObjectChangeActionChoices.ACTION_CREATE)

    def test_change_webhook_enqueued(self):

        with WebRequestContext(self.user):
            site = Site(name='Test Site 2')
            site.save()

        # Verify that a job was queued for the object creation webhook
        site = Site.objects.get(name='Test Site 2')
        self.assertEqual(self.queue.count, 1)
        job = self.queue.jobs[0]
        self.assertEqual(job.args[0], Webhook.objects.get(type_create=True))
        self.assertEqual(job.args[1]['id'], site.pk)
        self.assertEqual(job.args[2], 'site')
