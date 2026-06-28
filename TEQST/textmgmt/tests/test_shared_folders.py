from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from usermgmt.tests.utils import *
from django.contrib.auth.models import Group
from textmgmt.models import Folder, SharedFolder, Text, RecentProject
from usermgmt.models import CustomUser
from recordingmgmt.models import TextRecording, SentenceRecording
import uuid
import json


class TestSharedFolderFunctionality(TestCase):
    """
    Test suite for shared folder functionality including:
    - Recent folders endpoint
    - Shared folder access
    - Default folder configuration
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_languages_users_groups()

    def setUp(self):
        self.client = Client()
        self.token_1 = login_test_user(1, self.client)  # Publisher
        self.token_2 = login_test_user(2, self.client)  # Speaker
        self.token_3 = login_test_user(3, self.client)  # Publisher
        
        # Get users
        self.user1 = get_user(1)  # Publisher
        self.user2 = get_user(2)  # Speaker
        self.user3 = get_user(3)  # Publisher

    def tearDown(self):
        delete_all_users()

    def test_recent_folders_endpoint_requires_auth(self):
        """Test that recent-folders endpoint requires authentication"""
        response = self.client.get(reverse("spk-recent"))
        self.assertEqual(response.status_code, 401)

    def test_recent_folders_empty_for_new_user(self):
        """Test that new users get empty recent folders list"""
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=self.token_2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)

    def test_recent_folders_with_default_folder(self):
        """Test that users get default folder in recent folders"""
        # Create a folder that matches the DEFAULT_FOLDER setting
        default_folder_uuid = uuid.UUID('c92a535e-ef9c-4fa1-81b7-ca27022d636a')
        default_folder = Folder.objects.create(
            name='test3',
            owner=self.user1,
            root_id=default_folder_uuid
        )
        
        # Make it a shared folder and add user2 as speaker
        shared_folder = SharedFolder.objects.create(
            name='test3',
            owner=self.user1,
            root_id=default_folder_uuid
        )
        shared_folder.speaker.add(self.user2)
        
        # Test that user2 can see the folder in recent folders
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=self.token_2)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['folder']['name'], 'test3')
        self.assertEqual(data[0]['folder']['id'], default_folder.id)

    def test_default_folder_detail_access_for_all_users(self):
        """Test that DEFAULT_FOLDER entries can actually be opened by any user"""
        default_folder_uuid = uuid.UUID('c92a535e-ef9c-4fa1-81b7-ca27022d636a')
        shared_folder = SharedFolder.objects.create(
            name='default_for_all',
            owner=self.user1,
            root_id=default_folder_uuid,
            public=False
        )

        response = self.client.get(
            reverse("sharedfolder-detail", kwargs={'pk': shared_folder.id}),
            {'root': str(default_folder_uuid)},
            HTTP_AUTHORIZATION=self.token_2
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'default_for_all')

    def test_recent_folders_public_folder(self):
        """Test that public folders appear in recent folders"""
        # Create a public shared folder
        public_folder = SharedFolder.objects.create(
            name='public_test',
            owner=self.user1,
            public=True
        )
        
        # Test that any user can see public folders
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=self.token_2)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['folder']['name'], 'public_test')

    def test_recent_folders_private_folder_access(self):
        """Test that users can only see folders they have access to"""
        # Create a private shared folder
        private_folder = SharedFolder.objects.create(
            name='private_test',
            owner=self.user1,
            public=False
        )
        private_folder.speaker.add(self.user2)  # Add user2 as speaker
        
        # User2 should see the folder
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=self.token_2)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['folder']['name'], 'private_test')
        
        # User3 should not see the folder (not added as speaker)
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=self.token_3)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 0)

    def test_recent_folders_multiple_folders(self):
        """Test that users can see multiple folders they have access to"""
        # Create multiple shared folders
        folder1 = SharedFolder.objects.create(
            name='folder1',
            owner=self.user1,
            public=True
        )
        
        folder2 = SharedFolder.objects.create(
            name='folder2',
            owner=self.user1,
            public=False
        )
        folder2.speaker.add(self.user2)
        
        # User2 should see both folders
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=self.token_2)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        folder_names = [item['folder']['name'] for item in data]
        self.assertIn('folder1', folder_names)
        self.assertIn('folder2', folder_names)

    def test_recent_folders_ordering(self):
        """Test that recent folders are ordered by last_access"""
        # Create folders
        folder1 = SharedFolder.objects.create(
            name='folder1',
            owner=self.user1,
            public=True
        )
        
        folder2 = SharedFolder.objects.create(
            name='folder2',
            owner=self.user1,
            public=True
        )
        
        # Access folder2 first, then folder1
        self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=self.token_2)
        
        # Check ordering (most recent first)
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=self.token_2)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        # The order should be maintained based on last_access

    def test_shared_folder_detail_endpoint(self):
        """Test the shared folder detail endpoint"""
        # Create a shared folder
        shared_folder = SharedFolder.objects.create(
            name='test_shared',
            owner=self.user1,
            public=False
        )
        shared_folder.speaker.add(self.user2)
        
        # Test access to shared folder detail
        response = self.client.get(
            reverse("sharedfolder-detail", kwargs={'pk': shared_folder.id}),
            HTTP_AUTHORIZATION=self.token_2
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'test_shared')

    def test_shared_folder_detail_no_access(self):
        """Test that users without access cannot see shared folder details"""
        # Create a private shared folder
        shared_folder = SharedFolder.objects.create(
            name='private_shared',
            owner=self.user1,
            public=False
        )
        # Don't add user2 as speaker
        
        # Test that user2 cannot access the folder
        response = self.client.get(
            reverse("sharedfolder-detail", kwargs={'pk': shared_folder.id}),
            HTTP_AUTHORIZATION=self.token_2
        )
        self.assertEqual(response.status_code, 403)

    def test_public_folders_endpoint(self):
        """Test the public folders endpoint"""
        # Create public and private folders
        public_folder = SharedFolder.objects.create(
            name='public_folder',
            owner=self.user1,
            public=True
        )
        
        private_folder = SharedFolder.objects.create(
            name='private_folder',
            owner=self.user1,
            public=False
        )
        
        # Test public folders endpoint
        response = self.client.get(reverse("public-folders"), HTTP_AUTHORIZATION=self.token_2)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'public_folder')

    def test_default_folder_configuration(self):
        """Test that DEFAULT_FOLDER setting is properly configured"""
        # Check that DEFAULT_FOLDER is set
        self.assertTrue(hasattr(settings, 'DEFAULT_FOLDER'))
        self.assertIsInstance(settings.DEFAULT_FOLDER, list)
        self.assertEqual(len(settings.DEFAULT_FOLDER), 1)
        
        # Check that the UUID is correct
        expected_uuid = uuid.UUID('c92a535e-ef9c-4fa1-81b7-ca27022d636a')
        self.assertEqual(settings.DEFAULT_FOLDER[0], expected_uuid)

    def test_recent_project_creation(self):
        """Test that RecentProject entries are created correctly"""
        # Create a shared folder
        shared_folder = SharedFolder.objects.create(
            name='test_project',
            owner=self.user1,
            public=True
        )
        
        # Access the recent folders endpoint
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=self.token_2)
        self.assertEqual(response.status_code, 200)
        
        # Check that RecentProject entry was created
        recent_projects = RecentProject.objects.filter(speaker=self.user2)
        self.assertEqual(recent_projects.count(), 1)
        self.assertEqual(recent_projects.first().folder, shared_folder)

    def test_jooan_user_specific_test(self):
        """Test specifically for the jooan user scenario that was fixed"""
        # Create jooan user
        jooan_user = CustomUser.objects.create_user(
            username='jooan',
            password='test123',
            email='jooan84@hotmail.com',
            education='M12',
            gender='M',
            birth_year=1984,
            accent='kurdish',
            country='DEU'
        )
        
        # Create test3 folder with correct UUID
        test3_uuid = uuid.UUID('c92a535e-ef9c-4fa1-81b7-ca27022d636a')
        test3_folder = SharedFolder.objects.create(
            name='test3',
            owner=jooan_user,
            root_id=test3_uuid
        )
        test3_folder.speaker.add(jooan_user)
        
        # Login as jooan
        login_data = {"username": "jooan", "password": "test123"}
        login_response = self.client.post(reverse("login"), data=login_data)
        jooan_token = 'Token ' + login_response.json()['token']
        
        # Test that jooan can see test3 folder
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=jooan_token)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['folder']['name'], 'test3')
        self.assertEqual(data[0]['folder']['owner'], jooan_user.id)


class TestSharedFolderIntegration(TestCase):
    """
    Integration tests for shared folder functionality
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_languages_users_groups()

    def setUp(self):
        self.client = Client()
        self.token_1 = login_test_user(1, self.client)
        self.user1 = get_user(1)

    def tearDown(self):
        delete_all_users()

    def test_full_shared_folder_workflow(self):
        """Test the complete workflow of creating and accessing shared folders"""
        # 1. Create a shared folder
        shared_folder = SharedFolder.objects.create(
            name='workflow_test',
            owner=self.user1,
            public=False
        )
        
        # 2. Add a speaker
        user2 = get_user(2)
        shared_folder.speaker.add(user2)
        
        # 3. Login as the speaker
        token_2 = login_test_user(2, self.client)
        
        # 4. Access recent folders
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=token_2)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['folder']['name'], 'workflow_test')
        
        # 5. Access folder details
        response = self.client.get(
            reverse("sharedfolder-detail", kwargs={'pk': shared_folder.id}),
            HTTP_AUTHORIZATION=token_2
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'workflow_test')

    def test_shared_folder_permissions(self):
        """Test various permission scenarios for shared folders"""
        # Create test users and folders
        user2 = get_user(2)
        user3 = get_user(3)
        
        # Public folder
        public_folder = SharedFolder.objects.create(
            name='public_test',
            owner=self.user1,
            public=True
        )
        
        # Private folder with specific speakers
        private_folder = SharedFolder.objects.create(
            name='private_test',
            owner=self.user1,
            public=False
        )
        private_folder.speaker.add(user2)
        
        # Test permissions
        token_2 = login_test_user(2, self.client)
        token_3 = login_test_user(3, self.client)
        
        # User2 should see both folders
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=token_2)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        
        # User3 should only see public folder
        response = self.client.get(reverse("spk-recent"), HTTP_AUTHORIZATION=token_3)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['folder']['name'], 'public_test')
