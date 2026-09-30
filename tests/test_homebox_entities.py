"""Mocked Homebox entities API contract tests; these never make network requests."""

import sys
import types
import unittest
import os
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

try:
    import requests
except ModuleNotFoundError:
    requests = types.ModuleType('requests')
    requests.exceptions = types.SimpleNamespace(RequestException=RuntimeError)
    requests.get = Mock()
    requests.post = Mock()
    requests.put = Mock()
    sys.modules['requests'] = requests
    try:
        from homebox_client import HomeboxClient
    finally:
        del sys.modules['requests']
else:
    from homebox_client import HomeboxClient

import homebox_client
from homebox_errors import PartialEntityUpdateError


def response(status, body):
    result = Mock(status_code=status, text='')
    result.json.return_value = body
    return result


class HomeboxEntitiesContractTests(unittest.TestCase):
    def setUp(self):
        self.client = HomeboxClient.__new__(HomeboxClient)
        self.client.base_url = 'https://homebox.example.test'
        self.client.headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer test-token',
        }
        self.client.token = 'Bearer test-token'

    @patch.object(homebox_client.requests, 'put')
    @patch.object(homebox_client.requests, 'post')
    def test_create_item_posts_entity_then_full_update(self, post, put):
        created = {
            'id': 'entity-1',
            'name': 'Camera',
            'description': 'Mirrorless camera',
            'quantity': 1,
            'parent': {'id': 'location-1'},
            'entityType': {'id': 'item-type'},
            'tags': [{'id': 'tag-1'}],
            'purchasePrice': 0,
            'manufacturer': 'Example',
            'modelNumber': 'C-1',
            'serialNumber': '',
            'fields': [],
        }
        updated = dict(created, purchasePrice=249.99, purchaseFrom='Example Store')
        post.return_value = response(201, created)
        put.return_value = response(200, updated)

        result = self.client.create_item({
            'name': 'Camera',
            'description': 'Mirrorless camera',
            'quantity': 1,
            'locationId': 'location-1',
            'purchasePrice': 249.99,
            'purchaseFrom': 'Example Store',
            'purchaseTime': '2026-09-30',
            'manufacturer': 'Example',
            'modelNumber': 'C-1',
            'serialNumber': 'serial-9',
            'labelIds': ['tag-1'],
        })

        self.assertEqual(result, updated)
        post.assert_called_once_with(
            'https://homebox.example.test/api/v1/entities',
            headers=self.client.headers,
            json={
                'name': 'Camera',
                'parentId': 'location-1',
                'description': 'Mirrorless camera',
                'quantity': 1,
                'tagIds': ['tag-1'],
                'modelNumber': 'C-1',
                'manufacturer': 'Example',
            },
            timeout=30,
        )
        update_payload = put.call_args.kwargs['json']
        self.assertEqual(put.call_args.args[0], 'https://homebox.example.test/api/v1/entities/entity-1')
        self.assertEqual(update_payload['parentId'], 'location-1')
        self.assertEqual(update_payload['tagIds'], ['tag-1'])
        self.assertEqual(update_payload['purchasePrice'], 249.99)
        self.assertEqual(update_payload['purchaseFrom'], 'Example Store')
        self.assertEqual(update_payload['purchaseDate'], '2026-09-30')
        self.assertEqual(update_payload['serialNumber'], 'serial-9')
        self.assertNotIn('locationId', update_payload)
        self.assertNotIn('labelIds', update_payload)
        self.assertNotIn('purchaseTime', update_payload)
        self.assertEqual(set(update_payload), {
            'id', 'name', 'description', 'serialNumber', 'modelNumber',
            'manufacturer', 'warrantyDetails', 'warrantyExpires',
            'purchaseFrom', 'soldTo', 'soldNotes', 'notes', 'tagIds',
            'fields', 'assetId', 'quantity', 'purchasePrice', 'soldPrice',
            'parentId', 'entityTypeId', 'insured', 'archived',
            'syncChildEntityLocations', 'lifetimeWarranty', 'purchaseDate',
            'soldDate',
        })

    @patch.object(homebox_client.requests, 'put')
    @patch.object(homebox_client.requests, 'post')
    def test_create_item_raises_if_required_purchase_update_fails(self, post, put):
        created = {
            'id': 'entity-partial',
            'name': 'Camera',
            'description': 'Mirrorless camera',
            'quantity': 1,
            'parent': {'id': 'location-1'},
            'entityType': {'id': 'item-type'},
            'tags': [],
            'fields': [],
        }
        post.return_value = response(201, created)
        failed_update = response(500, {})
        failed_update.raise_for_status.side_effect = (
            homebox_client.requests.exceptions.RequestException('update failed')
        )
        put.return_value = failed_update

        with self.assertRaises(PartialEntityUpdateError) as raised:
            self.client.create_item({
                'name': 'Camera',
                'locationId': 'location-1',
                'purchasePrice': 249.99,
            })

        self.assertEqual(raised.exception.entity_id, 'entity-partial')
        post.assert_called_once()
        put.assert_called_once()

    @patch.object(homebox_client.requests, 'get')
    def test_locations_use_paginated_entity_query(self, get):
        get.side_effect = [
            response(200, {
                'items': [{'id': 'loc-1', 'name': 'Office'}],
                'page': 1,
                'pageSize': 100,
                'total': 2,
            }),
            response(200, {
                'items': [{'id': 'loc-2', 'name': 'Garage'}],
                'page': 2,
                'pageSize': 100,
                'total': 2,
            }),
        ]

        self.assertEqual([loc['id'] for loc in self.client.get_locations()], ['loc-1', 'loc-2'])
        self.assertEqual(get.call_count, 2)
        for page, call in enumerate(get.call_args_list, start=1):
            self.assertEqual(call.args[0], 'https://homebox.example.test/api/v1/entities')
            self.assertEqual(call.kwargs['params'], {
                'isLocation': 'true',
                'page': page,
                'pageSize': 100,
            })

    @patch.object(homebox_client.requests, 'get')
    def test_item_query_and_detail_use_entities_routes(self, get):
        listing = {'items': [{'id': 'item-1'}], 'page': 1, 'pageSize': 50, 'total': 1}
        detail = {'id': 'item-1', 'parent': {'id': 'loc-1'}, 'tags': []}
        get.side_effect = [response(200, listing), response(200, detail)]

        self.assertEqual(self.client.get_items(page=2, page_size=25), listing)
        self.assertEqual(self.client.get_item('item-1'), detail)
        self.assertEqual(get.call_args_list[0].args[0], 'https://homebox.example.test/api/v1/entities')
        self.assertEqual(get.call_args_list[0].kwargs['params'], {'page': 2, 'pageSize': 25})
        self.assertEqual(get.call_args_list[1].args[0], 'https://homebox.example.test/api/v1/entities/item-1')

    @patch.object(homebox_client.requests, 'post')
    def test_attachment_upload_uses_entity_route_and_multipart_contract(self, post):
        post.return_value = response(201, {'id': 'entity-1'})

        result = self.client.upload_attachment(
            'entity-1', b'%PDF', 'receipt.pdf', attachment_type='attachment'
        )

        self.assertEqual(result, {'id': 'entity-1'})
        post.assert_called_once_with(
            'https://homebox.example.test/api/v1/entities/entity-1/attachments',
            headers={'Authorization': 'Bearer test-token'},
            files={'file': ('receipt.pdf', b'%PDF', 'application/pdf')},
            data={'type': 'attachment', 'name': 'receipt.pdf'},
            timeout=30,
        )

    @patch.object(homebox_client.requests, 'put')
    @patch.object(homebox_client.requests, 'get')
    def test_label_compatibility_uses_tags_and_entity_update(self, get, put):
        entity = {
            'id': 'entity-1',
            'name': 'Camera',
            'parent': {'id': 'loc-1'},
            'entityType': {'id': 'item-type'},
            'tags': [{'id': 'existing-tag'}],
            'fields': [],
        }
        get.return_value = response(200, entity)
        put.return_value = response(200, entity)

        self.assertTrue(self.client.add_label_to_item('entity-1', 'new-tag'))
        self.assertEqual(get.call_args.args[0], 'https://homebox.example.test/api/v1/entities/entity-1')
        self.assertEqual(put.call_args.args[0], 'https://homebox.example.test/api/v1/entities/entity-1')
        self.assertEqual(put.call_args.kwargs['json']['tagIds'], ['existing-tag', 'new-tag'])

    @patch.object(homebox_client.requests, 'get')
    def test_labels_list_route_is_tags(self, get):
        tags = [{'id': 'tag-1', 'name': 'Verify Image'}]
        get.return_value = response(200, tags)

        self.assertEqual(self.client.get_labels(), tags)
        self.assertEqual(get.call_args.args[0], 'https://homebox.example.test/api/v1/tags')

    @patch.object(homebox_client.requests, 'post')
    def test_label_creation_uses_tag_endpoint(self, post):
        created = {'id': 'tag-1', 'name': 'Verify Image'}
        post.return_value = response(201, created)

        self.assertEqual(
            self.client.create_label(
                'Verify Image',
                description='Check the photo',
                color='#F59E0B',
            ),
            created,
        )
        post.assert_called_once_with(
            'https://homebox.example.test/api/v1/tags',
            headers=self.client.headers,
            json={
                'name': 'Verify Image',
                'description': 'Check the photo',
                'color': '#F59E0B',
            },
            timeout=10,
        )


    @patch.object(homebox_client.requests, 'post')
    def test_api_key_auth_skips_password_login_and_sets_bearer_header(self, post):
        with patch.dict(os.environ, {
            'HOMEBOX_URL': 'https://homebox.example.test/',
            'HOMEBOX_API_KEY': 'dedicated-service-key',
            'HOMEBOX_USERNAME': 'must-not-be-used',
            'HOMEBOX_PASSWORD': 'must-not-be-used',
        }, clear=True):
            client = HomeboxClient()

        self.assertEqual(client.headers['Authorization'], 'Bearer dedicated-service-key')
        post.assert_not_called()

    @patch.object(homebox_client.requests, 'post')
    def test_api_key_with_bearer_prefix_is_not_double_prefixed(self, post):
        with patch.dict(os.environ, {
            'HOMEBOX_URL': 'https://homebox.example.test',
            'HOMEBOX_API_KEY': 'Bearer already-prefixed-key',
        }, clear=True):
            client = HomeboxClient()

        self.assertEqual(client.headers['Authorization'], 'Bearer already-prefixed-key')
        post.assert_not_called()

    @patch.object(homebox_client.requests, 'post')
    def test_password_login_fallback_sets_bearer_header(self, post):
        post.return_value = response(200, {'token': 'session-token'})
        with patch.dict(os.environ, {
            'HOMEBOX_URL': 'https://homebox.example.test',
            'HOMEBOX_USERNAME': 'service-account',
            'HOMEBOX_PASSWORD': 'test-password',
            'HOMEBOX_API_KEY': '',
        }, clear=True):
            client = HomeboxClient()

        self.assertEqual(client.headers['Authorization'], 'Bearer session-token')
        post.assert_called_once_with(
            'https://homebox.example.test/api/v1/users/login',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={'username': 'service-account', 'password': 'test-password'},
            timeout=10,
        )


if __name__ == '__main__':
    unittest.main()
