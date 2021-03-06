import pytest
from channels.testing import WebsocketCommunicator
from django.test import Client
from guardian.models import Group as PermGroup
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from .models import Leaf, Hub, Datastore
import logging
import json
from sentinel.routing import application

logging.disable(logging.ERROR)

class ConsumerTests:
    @pytest.yield_fixture(autouse=True)
    async def disconnect(self):
        to_disconnect = []
        yield to_disconnect
        for client in to_disconnect:
            await client.disconnect()

    def create_hub(self, name):
        hub = Hub(name=name)
        hub.save()
        hub_group = PermGroup.objects.get(name="hub-" + str(hub.id))
        self.user.groups.add(hub_group)
        return hub
    
    def create_user_and_client(self):
        self.client = Client()
        self.user = User.objects.create_superuser(username="admin", password="password", email="admin@admin.om")
        self.client.login(username="admin", password="password")

    async def send_create_leaf(self, name, model, uuid, hub, api_version="0.1.0", receive=True):
        token_response = self.client.post(f"/hub/{hub.id}/register", {'uuid': uuid})
        token = json.loads(token_response.content)['token']
        client = WebsocketCommunicator(application, f"hub/{hub.id}")

        accepted, timeout = await client.connect()
        assert accepted, "Client connection was not accepted"

        config_message = {'type': 'CONFIG',
                          'name': name,
                          'model': model,
                          'uuid': uuid,
                          'token': token,
                          'api_version': api_version}
        await client.send_json_to(config_message)
        if receive:
            response = await client.receive_json_from()
            assert response is not None, "Expected a response"
            assert response['type'] == 'CONFIG_COMPLETE'
            response = await client.receive_json_from()
            assert response is not None, "Expected a response"
            assert response['type'] == 'LIST_DEVICES'
            assert await client.receive_nothing()
            
        try:
            db_leaf = Leaf.objects.get(uuid=uuid, hub=hub)
        except ObjectDoesNotExist:
            db_leaf = None
        
        assert db_leaf is not None, "Failed to find leaf in db after creation"

        return client, db_leaf

    @staticmethod
    async def send_device_update(client, sender, device, value, format, mode="IN", options=None, units=None):
        device_message = {'type': 'DEVICE_STATUS',
                          'uuid': sender,
                          'device': device,
                          'mode': mode,
                          'format': format,
                          'value': value}
        if options:
            device_message['options'] = options
        if units:
            device_message['units'] = units
        await client.send_json_to(device_message)
        await client.receive_nothing()

    @staticmethod
    async def send_subscribe(observer_client, observer_uuid, other_uuid, other_device):
        sub_message = {'type': 'SUBSCRIBE',
                       'uuid': observer_uuid,
                       'sub_uuid': other_uuid,
                       'sub_device': other_device}
        await observer_client.send_json_to(sub_message)
        assert await observer_client.receive_nothing()

    @staticmethod
    async def send_unsubscribe(observer_client, observer_uuid, other_uuid, other_device):
        sub_message = {'type': 'UNSUBSCRIBE',
                       'uuid': observer_uuid,
                       'sub_uuid': other_uuid,
                       'sub_device': other_device}
        await observer_client.send_json_to(sub_message)
        assert await observer_client.receive_nothing()

    async def assertDatastoreReadSuccess(self, client, requester, name, expected_value=None, expected_format=None):
        await self.send_get_datastore(client, requester, name)
        expected_response = {
            'type': 'DATASTORE_VALUE',
            'name': name,
            'value': expected_value,  # value should not have changed from last set request
            'format': expected_format
        }
        response = await client.receive_json_from()
        assert response is not None, "Expected a response after requesting data"
        assert response['type'] == expected_response['type']
        assert response['name'] == expected_response['name']
        assert response['value'] == expected_response['value']
        assert response['format'] == expected_response['format']

    async def assertDatastoreReadFailed(self, client, requester, name):
        await self.send_get_datastore(client, requester, name)
        expected_response = {
            'type': 'PERMISSION_DENIED',
            'request': 'DATASTORE_GET',
            'name': name,
        }
        response = await client.receive_json_from()
        assert response is not None, "Expected a response"
        assert response['type'] == expected_response['type']
        assert response['request'] == expected_response['request']
        assert response['name'] == expected_response['name']

    async def assertDatastoreSetFailed(self, client, requester, name, value):
        await self.send_set_datastore(client, requester, name, value)
        expected_response = {
            'type': 'PERMISSION_DENIED',
            'request': 'DATASTORE_SET',
            'name': name,
        }
        response = await client.receive_json_from()
        assert response is not None, "Expected a response from setting datastore value"
        assert response['type'] == expected_response['type']
        assert response['request'] == expected_response['request']
        assert response['name'] == expected_response['name']

    async def assertDatastoreDeleteFailed(self, client, requester, name):
        await self.send_delete_datastore(client, requester, name)
        expected_response = {
            'type': 'PERMISSION_DENIED',
            'request': 'DATASTORE_DELETE',
            'name': name,
        }
        response = await client.receive_json_from()
        assert response is not None, "Expected a response from deleting datastore value"
        assert response['type'] == expected_response['type']
        assert response['request'] == expected_response['request']
        assert response['name'] == expected_response['name']

    async def assertUnknownDatastore(self, client, requester, name, method='GET', set_value=None):
        if method == 'GET':
            await self.send_get_datastore(client, requester, name)
        else:
            await self.send_set_datastore(client, requester, name, set_value)
        expected_response = {
            'type': 'UNKNOWN_DATASTORE',
            'request': 'DATASTORE_' + method,
            'name': name,
        }
        response = await client.receive_json_from()
        assert response['type'] == expected_response['type']
        assert response['request'] == expected_response['request']
        assert response['name'] == expected_response['name']

    @staticmethod
    async def send_create_datastore(client, requester, name, value, format, permissions={}, handle=True):
        data_message = {
            'type': 'DATASTORE_CREATE',
            'uuid': requester,
            'name': name,
            'value': value,
            'format': format,
        }
        if permissions:
            data_message['permissions'] = permissions

        await client.send_json_to(data_message)

        if handle:
            assert await client.receive_json_from()

    @staticmethod
    async def send_delete_datastore(client, requester, name):
        data_message = {
            'type': 'DATASTORE_DELETE',
            'uuid': requester,
            'name': name,
        }
        await client.send_json_to(data_message)

    @staticmethod
    async def send_set_datastore(client, requester, name, value):
        data_message = {
            'type': 'DATASTORE_SET',
            'uuid': requester,
            'name': name,
            'value': value
        }
        await client.send_json_to(data_message)

    @staticmethod
    async def send_get_datastore(client, requester, name):
        data_message = {
            'type': 'DATASTORE_GET',
            'uuid': requester,
            'name': name
        }
        await client.send_json_to(data_message)

    @staticmethod
    async def send_create_condition(admin_client, admin_uuid, condition_name, predicate, actions, handle=True):
        message = {'type': 'CONDITION_CREATE',
                   'uuid': admin_uuid,
                   'name': condition_name,
                   'predicate': predicate,
                   'actions': actions
                   }
        await admin_client.send_json_to(message)
        if handle:
            await admin_client.receive_nothing(timeout=2)

    @staticmethod
    def create_action(action_type, action_target, action_device, action_value=None):
        action = {
            'action_type': action_type,
            'target': action_target,
            'device': action_device
        }
        if action_value is not None:
            action['value'] = action_value
        return action

    @staticmethod
    async def send_delete_condition(admin_client, admin_uuid, condition_name):
        message = {'type': 'CONDITION_DELETE',
                   'uuid': admin_uuid,
                   'name': condition_name}
        await admin_client.send_json_to(message)
        assert await admin_client.receive_nothing()

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestLeaves(ConsumerTests):
    async def test_create(self, disconnect):
        """
        Tests creating a leaf
        """
        self.create_user_and_client()

        hub = self.create_hub("test_hub")
        name = "py_create_test"
        model = "01"
        uuid = "a581b491-da64-4895-9bb6-5f8d76ebd44e"
        api_version = "3.2.3"
        client, db_leaf = await self.send_create_leaf(name, model, uuid, hub, api_version)
        disconnect.append(client)

        assert db_leaf.name == name, "Wrong name"
        assert db_leaf.model == model, "Wrong model"
        assert db_leaf.uuid == uuid, "Wrong uuid"
        assert db_leaf.api_version == api_version, "Wrong api_version"


    async def test_create_number_device(self, disconnect):
        self.create_user_and_client()

        hub = self.create_hub("test_hub")
        name = "py_device_test"
        model = "01"
        uuid = "a581b491-da64-4895-9bb6-5f8d76ebd44e"
        client, db_leaf = await self.send_create_leaf(name, model, uuid, hub)
        disconnect.append(client)

        await self.send_device_update(client, db_leaf.uuid, 'rfid_reader', 31231, 'number', "IN", {'auto': 1})

        assert db_leaf.devices.count() == 1, "Expected one device"
        devices = {device.name: device for device in db_leaf.devices.all()}

        assert 'rfid_reader' in devices  # tests name implicitly
        rfid_device = devices['rfid_reader']
        assert rfid_device.format == 'number', "Expected rfid to be a number device"
        assert rfid_device.value == 31231, "Wrong value"


    async def test_create_bool_device(self, disconnect):
        self.create_user_and_client()

        hub = self.create_hub("test_hub")
        name = "py_device_test"
        model = "01"
        uuid = "a581b491-da64-4895-9bb6-5f8d76ebd44e"
        client, db_leaf = await self.send_create_leaf(name, model, uuid, hub)
        disconnect.append(client)

        await self.send_device_update(client, db_leaf.uuid, 'bool_test', True, 'bool', "IN", {'auto': 1})
        assert db_leaf.devices.count() == 1, "Expected one device"
        devices = {device.name: device for device in db_leaf.devices.all()}

        assert 'bool_test' in devices  # tests name implicitly
        bool_test = devices['bool_test']
        assert bool_test.format == 'bool', "Expected test to be a bool device"
        assert bool_test.value == True, "Wrong value"


    async def test_create_string_device(self, disconnect):
        self.create_user_and_client()

        hub = self.create_hub("test_hub")
        name = "py_device_test"
        model = "01"
        uuid = "a581b491-da64-4895-9bb6-5f8d76ebd44e"
        client, db_leaf = await self.send_create_leaf(name, model, uuid, hub)
        disconnect.append(client)

        await self.send_device_update(client, db_leaf.uuid, 'string_dev', 'this is a test', 'string', "IN", {'auto': 1})
        assert db_leaf.devices.count() == 1, 'Expected one device'
        devices = {device.name: device for device in db_leaf.devices.all()}

        assert 'string_dev' in devices  # tests name implicitly
        string_dev = devices['string_dev']
        assert string_dev.format == 'string', "Expected test to be a string device"
        assert string_dev.value == 'this is a test', "Wrong value"

    async def test_create_multiple_devices(self, disconnect):
        self.create_user_and_client()

        hub = self.create_hub("test_hub")
        name = "py_device_test"
        model = "01"
        uuid = "a581b491-da64-4895-9bb6-5f8d76ebd44e"
        client, db_leaf = await self.send_create_leaf(name, model, uuid, hub)
        disconnect.append(client)

        # send initial values, create devices in database
        await self.send_device_update(client, db_leaf.uuid, 'rfid_reader', 125, 'number', "IN", {'auto': 1})
        await self.send_device_update(client, db_leaf.uuid, 'door', False, 'bool', "OUT")
        await self.send_device_update(client, db_leaf.uuid, 'thermometer', 50, 'number+units', "IN", {'auto': 1}, units="F")
        await self.send_device_update(client, db_leaf.uuid, 'led_display', "BLUE LIGHT MODE", 'string', "OUT", {'auto': 1})

        assert db_leaf.devices.count() == 4, "Expected four devices"
        devices = {device.name: device for device in db_leaf.devices.all()}
        # test all devices
        assert 'rfid_reader' in devices  # tests name implicitly
        rfid_device = devices['rfid_reader']
        assert rfid_device.format == 'number', "Expected rfid to be a number device"
        assert rfid_device.value == 125, "Wrong value"
        # self.assertDictEqual({'auto': 1}, rfid_device.options, "Wrong options dictionary")

        assert 'door' in devices
        door_device = devices['door']
        assert door_device.format == 'bool', "Expected door to be a boolean device"
        assert door_device.value == 0, "Wrong value"
        # self.assertDictEqual({}, door_device.options, "Wrong options dictionary")

        assert 'thermometer' in devices
        thermometer_device = devices['thermometer']
        assert thermometer_device.format == 'number+units', "Expected device to be a number+unit device"
        assert thermometer_device.value == 50, "Wrong value"
        # self.assertDictEqual({'auto': 1}, thermometer_devide.options, "Wrong options dictionary")

        assert 'led_display' in devices
        led_device = devices['led_display']
        assert led_device.format == 'string', "Expected device to be a number+unit device"
        assert led_device.value == "BLUE LIGHT MODE", "Wrong value"
        # self.assertDictEqual({'auto': 1}, led_device.options, "Wrong options dictionary")


    async def test_update_device_multiple(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        name = "py_device_test"
        model = "01"
        uuid = "a581b491-da64-4895-9bb6-5f8d76ebd44e"
        client, db_leaf = await self.send_create_leaf(name, model, uuid, hub)
        disconnect.append(client)

        await self.send_device_update(client, db_leaf.uuid, 'rfid_reader', 125, 'number', "IN", {'auto': 1})
        await self.send_device_update(client, db_leaf.uuid, 'door', False, 'bool', "OUT")
        await self.send_device_update(client, db_leaf.uuid, 'thermometer', 50, 'number+units', "IN", {'auto': 1}, units="F")
        await self.send_device_update(client, db_leaf.uuid, 'led_display', "BLUE LIGHT MODE", 'string', "OUT", {'auto': 1})

        # test updating by updating all but door
        await self.send_device_update(client, db_leaf.uuid, 'rfid_reader', 33790, 'number', "IN", {'auto': 1})
        await self.send_device_update(client, db_leaf.uuid, 'thermometer', 90, 'number+units', "IN", {'auto': 1}, units="F")
        await self.send_device_update(client, db_leaf.uuid, 'led_display', "HERE WE", 'string', "OUT", {'auto': 1})

        devices = {device.name: device for device in db_leaf.devices.all()}
        rfid_device = devices['rfid_reader']
        door_device = devices['door']
        thermometer_device = devices['thermometer']
        led_device = devices['led_display']

        assert rfid_device.value == 33790, "Wrong value"
        assert door_device.value == False, "Wrong value"  # make sure door didn't change
        assert led_device.value == "HERE WE", "Wrong value"
        assert thermometer_device.value == 90, "Wrong value"


    @pytest.mark.skip("Options not implemented yet")
    def test_options(self, disconnect):
        pass


    async def test_subscribe(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")

        # setup leaves
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        observer_client, observer_leaf = await self.send_create_leaf('rfid_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(observer_client)

        # setup devices
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')

        # subscribe
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'rfid_reader')
        assert await rfid_client.receive_nothing()


    async def test_subscription(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        observer_client, observer_leaf = await self.send_create_leaf('rfid_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(observer_client)

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'rfid_reader')

        # update rfid device
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042781, 'number')
        assert await rfid_client.receive_nothing(), "Didn't  expect a response"

        # test that subscription message was received and check parameters
        sub_message = await observer_client.receive_json_from()
        assert sub_message is not None, "Expected to receive a subscription update"
        assert sub_message['type'] == 'SUBSCRIPTION_UPDATE', "Wrong type"
        assert sub_message['sub_uuid'] == rfid_leaf.uuid, "Wrong uuid"
        assert sub_message['sub_device'] == 'rfid_reader', "Wrong device"
        sub_status = {'type': 'DEVICE_STATUS',
                      'device': 'rfid_reader',
                      'format': 'number',
                      'value': 3032042781}

        for key in sub_status:  # check that the message has the right values
            assert sub_message['message'][key] == sub_status[key]

        assert await rfid_client.receive_nothing(), "Didn't  expect a response"  # make sure there are no more messages

        # make sure other device doesn't trigger subscription event
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')
        assert await observer_client.receive_nothing(), "Didn't  expect a response"
        assert await rfid_client.receive_nothing(), "Didn't  expect a response"


    async def test_full_leaf_subscribe(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        observer_client, observer_leaf = await self.send_create_leaf('rfid_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(observer_client)

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3790, 'number')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')

        # subscribe to the rfid reader
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'rfid_reader')
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'leaf')

        assert await observer_client.receive_nothing()
        assert await rfid_client.receive_nothing()


    async def test_full_leaf_subscription(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        observer_client, observer_leaf = await self.send_create_leaf('rfid_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3790, 'number')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')

        # subscribe to the rfid reader
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'leaf')

        # test that other device generates subscription event
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', True, 'bool')
        sub_message = await observer_client.receive_json_from()

        assert sub_message['type'] == 'SUBSCRIPTION_UPDATE', "Wrong type"
        assert sub_message['sub_uuid'] == rfid_leaf.uuid, "Wrong uuid"
        assert sub_message['sub_device'] == 'leaf', "Wrong device"
        sub_status = {'type': 'DEVICE_STATUS',
                      'device': 'other_sensor',
                      'format': 'bool',
                      'value': True}

        for key in sub_status:
            assert sub_message['message'][key] == sub_status[key]

        assert await observer_client.receive_nothing(), "Didn't  expect a response"  # ensure there are no more messages

        await rfid_client.disconnect()
        await observer_client.disconnect()


    async def test_full_leaf_subscription_with_other(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        observer_client, observer_leaf = await self.send_create_leaf('rfid_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(observer_client)

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3790, 'number')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')

        # subscribe to the rfid reader
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'rfid_reader')
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'leaf')

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        sub_message = await observer_client.receive_json_from()
        assert sub_message is not None, "Expected to receive a subscription update"
        assert sub_message['type'] == 'SUBSCRIPTION_UPDATE', "Wrong type"
        assert sub_message['sub_uuid'] == rfid_leaf.uuid, "Wrong uuid"
        assert sub_message['sub_device'] == 'rfid_reader', "Wrong device"
        # ensure message doesn't show up twice
        assert await observer_client.receive_nothing(), "Didn't  expect a response"


    async def test_unsubscribe(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")

        # setup leaves
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)
        
        observer_client, observer_leaf =  await self.send_create_leaf('rfid_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(observer_client)

        # setup devices
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')

        # subscribe to rfid_leaf
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'rfid_reader')

        # update rfid device
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042781, 'number')
        assert await rfid_client.receive_nothing(), "Didn't  expect a response"

        # test that subscription message was received
        assert await observer_client.receive_nothing() is False, "Expected to receive a subscription update"
        await observer_client.receive_json_from()
        
        assert await observer_client.receive_nothing(), "Didn't  expect a response"  # make sure there are no more messages

        # unsubscribe
        await self.send_unsubscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'rfid_reader')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')

        assert (await observer_client.receive_nothing()) or not (await observer_client.receive_json_from()) # should not receive subscription updates any more


    async def test_full_leaf_unsubscribe_multi(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)
        
        observer_client, observer_leaf = await self.send_create_leaf('rfid_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(observer_client)

        # setup devices
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3790, 'number')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')

        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'leaf')
        assert await observer_client.receive_nothing(), "Didn't  expect a response"
        assert await rfid_client.receive_nothing(), "Didn't  expect a response"

        # unsubscribe and make sure other sensor doesn't generate subscription events anymore
        await self.send_unsubscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'leaf')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')
        assert await observer_client.receive_nothing(), "Did not expect a message from other_sensor after unsubscribing"

        # make sure that the original subscription to the rfid_reader still exists
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        assert await observer_client.receive_nothing(), "Did not expect a message from other_sensor after unsubscribing"


    async def test_full_leaf_unsubscribe_multiple(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)
        
        observer_client, observer_leaf = await self.send_create_leaf('rfid_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(observer_client)

        # setup devices
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3790, 'number')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')

        # subscribe to the rfid reader
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'rfid_reader')
        # subscribe to whole leaf
        await self.send_subscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'leaf')
        assert await observer_client.receive_nothing(), "Didn't  expect a response"
        assert await rfid_client.receive_nothing(), "Didn't  expect a response"

        # unsubscribe and make sure other sensor doesn't generate subscription events anymore
        await self.send_unsubscribe(observer_client, observer_leaf.uuid, rfid_leaf.uuid, 'leaf')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'other_sensor', False, 'bool')
        assert await observer_client.receive_nothing(), "Did not expect a message from other_sensor after unsubscribing"

        # make sure that the original subscription to the rfid_reader still exists
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        assert await observer_client.receive_json_from() is not None, "Expected to still receive a subscription update"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestDatastore(ConsumerTests):
    async def test_datastore_create(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        # make sure the datastore didn't exist beforehand
        await self.assertUnknownDatastore(rfid_client, rfid_leaf.uuid, 'sean_home', 'GET')
        await self.assertUnknownDatastore(rfid_client, rfid_leaf.uuid, 'sean_home', 'SET', False)

        # test create
        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool', handle=False)
        expected_response = {
            'type': 'DATASTORE_CREATED',
            'name': 'sean_home',
            'format': 'bool',
        }
        response = await rfid_client.receive_json_from()
        assert response is not None, "Expected a message for creating datastore"
        assert response['type'] == expected_response['type']
        assert response['name'] == expected_response['name']
        assert response['format'] == expected_response['format']

        # test making another with same number
        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', True, 'bool', handle=False)
        assert await rfid_client.receive_nothing()

        # make sure value was saved
        await self.assertDatastoreReadSuccess(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool')

    async def test_datastore_delete(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool')

        # test delete
        await self.send_delete_datastore(rfid_client, rfid_leaf.uuid, 'sean_home')
        expected_response = {
            'type': 'DATASTORE_DELETED',
            'name': 'sean_home'
        }

        response = await rfid_client.receive_json_from()
        assert response['type'] == expected_response['type']
        assert response['name'] == expected_response['name']

        # make sure delete was successful
        await self.assertUnknownDatastore(rfid_client, rfid_leaf.uuid, 'sean_home', 'GET')
        await self.assertUnknownDatastore(rfid_client, rfid_leaf.uuid, 'sean_home', 'SET', False)


    async def test_datastore_update(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool')
        
        # set new value and check for success with a read
        await self.assertDatastoreReadSuccess(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool')
        await self.send_set_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', True)
        await self.assertDatastoreReadSuccess(rfid_client, rfid_leaf.uuid, 'sean_home', True, 'bool')
        

    async def test_datastore_permissions_default_deny(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")

        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        other_client, other_leaf = await self.send_create_leaf('other_leaf', '0', '7cfb0bde-7b0e-430b-a033-034eb7422f4b', hub)
        disconnect.append(other_client)

        door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(door_client)

        light_client, light_leaf = await self.send_create_leaf('light_leaf', '0', '3cbb357f-3dda-4463-9055-581b82ab8690',  hub)
        disconnect.append(light_client)

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        permissions = {
            'default': 'deny',  # deny reads and writes by default
            door_leaf.uuid: 'read',  # the door can read the value
            light_leaf.uuid: 'write',  # the light can read and write
            admin_leaf.uuid: 'admin'
        }
        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool', permissions)

        await self.assertDatastoreReadFailed(other_client, other_leaf.uuid, 'sean_home')
        await self.assertDatastoreSetFailed(other_client, other_leaf.uuid, 'sean_home', True)
        await self.assertDatastoreDeleteFailed(other_client, other_leaf.uuid, 'sean_home')


    async def test_datastore_permissions_default_write(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        light_client, light_leaf = await self.send_create_leaf('light_leaf', '0', '3cbb357f-3dda-4463-9055-581b82ab8690',  hub)
        disconnect.append(light_client)

        permissions = {
            'default': 'write'
        }
        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool', permissions)

        # ensures reading with write permissions works and last 'set' was not successful
        await self.assertDatastoreReadSuccess(light_client, light_leaf.uuid, 'sean_home', False, 'bool')

        await self.send_set_datastore(light_client, light_leaf.uuid, 'sean_home', True)
        assert await light_client.receive_json_from(), "Expected new value update upon writing"

        await self.assertDatastoreReadSuccess(light_client, light_leaf.uuid, 'sean_home', True, 'bool')
        await self.assertDatastoreDeleteFailed(light_client, light_leaf.uuid, 'sean_home')

        
    @pytest.mark.skip("TODO: fix, update permissions api")
    async def test_datastore_permissions_deny(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(door_client)

        light_client, light_leaf = await self.send_create_leaf('light_leaf', '0', '3cbb357f-3dda-4463-9055-581b82ab8690',  hub)
        disconnect.append(light_client)

        other_client, other_leaf = await self.send_create_leaf('other_leaf', '0', '7cfb0bde-7b0e-430b-a033-034eb7422f4b', hub)
        disconnect.append(other_client)

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        permissions = {
            'default': 'write',  # deny reads and writes by default
            door_leaf.uuid: 'read',  # the door can read the value
            light_leaf.uuid: 'write',  # the light can read and write
            admin_leaf.uuid: 'admin',
            other_leaf.uuid: 'deny'
        }
        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool', permissions)

        await self.assertDatastoreReadFailed(other_client, other_leaf.uuid, 'sean_home')
        await self.assertDatastoreSetFailed(other_client, other_leaf.uuid, 'sean_home', True)
        await self.assertDatastoreDeleteFailed(other_client, other_leaf.uuid, 'sean_home')


    async def test_datastore_permissions_read(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(door_client)

        light_client, light_leaf = await self.send_create_leaf('light_leaf', '0', '3cbb357f-3dda-4463-9055-581b82ab8690',  hub)
        disconnect.append(light_client)

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        permissions = {
            'default': 'deny',  # deny reads and writes by default
            door_leaf.uuid: 'read',  # the door can read the value
            light_leaf.uuid: 'write',  # the light can read and write
            admin_leaf.uuid: 'admin'
        }
        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool', permissions)

        # test read
        await self.assertDatastoreReadSuccess(door_client, door_leaf.uuid, 'sean_home', False, 'bool')
        await self.assertDatastoreSetFailed(door_client, door_leaf.uuid, 'sean_home', True)
        await self.assertDatastoreDeleteFailed(door_client, door_leaf.uuid, 'sean_home')


    async def test_datastore_permissions_write(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(door_client)

        light_client, light_leaf = await self.send_create_leaf('light_leaf', '0', '3cbb357f-3dda-4463-9055-581b82ab8690',  hub)
        disconnect.append(light_client)

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        permissions = {
            'default': 'deny',  # deny reads and writes by default
            door_leaf.uuid: 'read',  # the door can read the value
            light_leaf.uuid: 'write',  # the light can read and write
            admin_leaf.uuid: 'admin'
        }
        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool', permissions)

        # ensures reading with write permissions works and last 'set' was not successful
        await self.assertDatastoreReadSuccess(light_client, light_leaf.uuid, 'sean_home', False, 'bool')

        await self.send_set_datastore(light_client, light_leaf.uuid, 'sean_home', True)
        assert await light_client.receive_json_from(), "Expected new value update upon writing"

        await self.assertDatastoreReadSuccess(light_client, light_leaf.uuid, 'sean_home', True, 'bool')
        await self.assertDatastoreDeleteFailed(light_client, light_leaf.uuid, 'sean_home')


    async def test_datastore_permissions_admin(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(door_client)

        light_client, light_leaf = await self.send_create_leaf('light_leaf', '0', '3cbb357f-3dda-4463-9055-581b82ab8690',  hub)
        disconnect.append(light_client)

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        permissions = {
            'default': 'deny',  # deny reads and writes by default
            door_leaf.uuid: 'read',  # the door can read the value
            light_leaf.uuid: 'write',  # the light can read and write
            admin_leaf.uuid: 'admin'
        }
        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'sean_home', False, 'bool', permissions)

        # test admin
        await self.send_set_datastore(admin_client, admin_leaf.uuid, 'sean_home', False)
        assert await admin_client.receive_json_from(), "Expected new value update upon writing"

        await self.assertDatastoreReadSuccess(admin_client, admin_leaf.uuid, 'sean_home', False, 'bool')
        await self.send_delete_datastore(admin_client, admin_leaf.uuid, 'sean_home')
        expected_response = {
            'type': 'DATASTORE_DELETED',
            'name': 'sean_home'
        }
        response = await admin_client.receive_json_from()
        assert response['type'] == expected_response['type']
        assert response['name'] == expected_response['name']

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestConditions(ConsumerTests):
    async def test_comparator_conditions(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")

        async def test_basic(operator, literal, initial, wrong, right):
            name = 'basic_' + operator + str(literal)

            admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
            disconnect.append(admin_client)

            rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
            disconnect.append(rfid_client)

            door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
            disconnect.append(door_client)

            await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', initial, 'number')
            await self.send_device_update(door_client, door_leaf.uuid, 'door_open', False, 'bool', mode='OUT')

            predicates = [operator, [rfid_leaf.uuid, 'rfid_reader'], literal]
            await self.send_create_condition(admin_client, admin_leaf.uuid, name,
                                             predicates, actions=[self.create_action('SET', door_leaf.uuid, 'door_open', action_value=True)])

            await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', wrong, 'number')
            assert await door_client.receive_nothing()  # condition has not been met yet
            await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', right, 'number')

            expected = {
                'type': 'SET_OUTPUT',
                'uuid': door_leaf.uuid,
                'device': 'door_open',
                'value': True,
                'format': 'bool'
            }
            response = await door_client.receive_json_from()
            assert response is not None, "Expected a SET_OUTPUT response from condition"
            assert expected['type'] == response['type']
            assert expected['uuid'] == response['uuid']
            assert expected['device'] == response['device']
            assert expected['value'] == response['value']
            assert expected['format'] == response['format']
            assert await door_client.receive_nothing()  # only gets one update
            await self.send_delete_condition(admin_client, admin_leaf.uuid, name)
            assert await admin_client.receive_nothing()

        await test_basic('=', 3032042781, 33790, 3032042780, 3032042781)
        await test_basic('!=', 3032042781, 3032042781, 3032042781, 33790)
        await test_basic('>', 0, -12, -5, 13)
        await test_basic('<', 0, 12, 5, -13)
        await test_basic('>=', 0, -12, -5, 0)
        await test_basic('<=', 0, 12, 5, 0)

    async def test_binary_and(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        other_client, other_leaf = await self.send_create_leaf('other_leaf', '0', '7cfb0bde-7b0e-430b-a033-034eb7422f4b', hub)
        disconnect.append(other_client)

        door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(door_client)

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(other_client, other_leaf.uuid, 'other_sensor', False, 'bool')
        await self.send_device_update(door_client, door_leaf.uuid, 'door_open', False, 'bool', mode='OUT')

        predicates = ['AND', [['=', [rfid_leaf.uuid, 'rfid_reader'], 3032042781],
                              ['=', [other_leaf.uuid, 'other_sensor'], True]]]
        await self.send_create_condition(admin_client, admin_leaf.uuid, 'binary_AND', predicates,
                                         actions=[self.create_action('SET', door_leaf.uuid, 'door_open', action_value=True)])

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042781, 'number')
        assert await door_client.receive_nothing()  # other_sensor is false so the condition doesn't trigger

        await self.send_device_update(other_client, other_leaf.uuid, 'other_sensor', True, 'bool')

        response = await door_client.receive_json_from()
        assert response is not None, "Expected a SET_OUTPUT response from condition"
        assert response['type'] == 'SET_OUTPUT'
        assert await door_client.receive_nothing()  # only gets one update
        await self.send_delete_condition(admin_client, admin_leaf.uuid, "binary_AND")

    async def test_binary_or(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        other_client, other_leaf = await self.send_create_leaf('other_leaf', '0', '7cfb0bde-7b0e-430b-a033-034eb7422f4b', hub)
        disconnect.append(other_client)

        door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(door_client)

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(other_client, other_leaf.uuid, 'other_sensor', False, 'bool')
        await self.send_device_update(door_client, door_leaf.uuid, 'door_open', False, 'bool', mode='OUT')

        predicates = ['OR', [['=', [rfid_leaf.uuid, 'rfid_reader'], 3032042781],
                             ['=', [other_leaf.uuid, 'other_sensor'], True]]]
        await self.send_create_condition(admin_client, admin_leaf.uuid, 'binary_OR', predicates,
                                         actions=[self.create_action('SET', door_leaf.uuid, 'door_open', action_value=True)])
       
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042781, 'number')
        assert await door_client.receive_json_from(), "Expected a response as one condition is true"

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042780, 'number')
        assert await door_client.receive_nothing(), "Expected no response as both conditions are false"

        await self.send_device_update(other_client, other_leaf.uuid, 'other_sensor', True, 'bool')
        assert await door_client.receive_json_from(), "Expected SET_OUTPUT as other condition is true"

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042781, 'number')

        assert await door_client.receive_nothing()  # only gets one update
        await self.send_delete_condition(admin_client, admin_leaf.uuid, "binary_OR")

    async def test_binary_xor(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        other_client, other_leaf = await self.send_create_leaf('other_leaf', '0', '7cfb0bde-7b0e-430b-a033-034eb7422f4b', hub)
        disconnect.append(other_client)

        door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(door_client)

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042781, 'number')
        await self.send_device_update(other_client, other_leaf.uuid, 'other_sensor', True, 'bool')
        await self.send_device_update(door_client, door_leaf.uuid, 'door_open', False, 'bool', mode='OUT')

        predicates = ['XOR', [['=', [rfid_leaf.uuid, 'rfid_reader'], 3032042781],
                              ['=', [other_leaf.uuid, 'other_sensor'], True]]]
        await self.send_create_condition(admin_client, admin_leaf.uuid, 'binary_OR', predicates,
                                   actions=[self.create_action('SET', door_leaf.uuid, 'door_open', action_value=True)])

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042781, 'number')
        assert await door_client.receive_nothing(), "Expected no response as both conditions are true"

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 12312, 'number')
        assert await door_client.receive_json_from(), "Expected a response as one condition is true"

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042781, 'number')
        assert await door_client.receive_nothing(), "Expected no response as both conditions are true"

        await self.send_device_update(other_client, other_leaf.uuid, 'other_sensor', False, 'bool')
        assert await door_client.receive_json_from(), "Expected a response as one condition is true"

        assert await door_client.receive_nothing()  # only gets one update
        await self.send_delete_condition(admin_client, admin_leaf.uuid, "binary_OR")

    async def test_nested(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")
        
        admin_client, admin_leaf = await self.send_create_leaf('third_client', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        third_client, third_leaf = await self.send_create_leaf('third_client', '0', 'ea0caf44-8099-4da5-8538-c208816527dc', hub)
        disconnect.append(third_client)

        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        other_client, other_leaf = await self.send_create_leaf('other_leaf', '0', '7cfb0bde-7b0e-430b-a033-034eb7422f4b', hub)
        disconnect.append(other_client)

        door_client, door_leaf = await self.send_create_leaf('door_leaf', '0', 'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub)
        disconnect.append(door_client)

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(other_client, other_leaf.uuid, 'other_sensor', False, 'bool')
        await self.send_device_update(third_client, third_leaf.uuid, 'third_sensor', False, 'bool')
        await self.send_device_update(door_client, door_leaf.uuid, 'door_open', False, 'bool', mode='OUT')

        predicates = ['OR', [['AND', [['=', [rfid_leaf.uuid, 'rfid_reader'], 3032042781],
                                      ['=', [third_leaf.uuid, 'third_sensor'], True]]],
                             ['=', [other_leaf.uuid, 'other_sensor'], True]]]

        await self.send_create_condition(admin_client, admin_leaf.uuid, 'binary_nested', predicates,
                                         actions=[self.create_action('SET', door_leaf.uuid, 'door_open', action_value=True)])

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 3032042781, 'number')
        assert await door_client.receive_nothing(), "Expected no response as only one nested condition is true"

        await self.send_device_update(third_client, third_leaf.uuid, 'third_sensor', True, 'bool')

        assert await door_client.receive_json_from(), "Expected SET_OUTPUT as both inner conditions are true"

        await self.send_device_update(third_client, third_leaf.uuid, 'third_sensor', False, 'bool')
        assert await door_client.receive_nothing(), "Expected no response as only one nested condition is true"

        await self.send_device_update(other_client, other_leaf.uuid, 'other_sensor', True, 'false')
        assert await door_client.receive_json_from(), "Expected a response as one outer condition is true"

        assert await door_client.receive_nothing()  # only gets one update
        await self.send_delete_condition(admin_client, admin_leaf.uuid, "binary_nested")

    async def test_invalid_output_device(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        other_client, other_leaf = await self.send_create_leaf('other_leaf', '0', '7cfb0bde-7b0e-430b-a033-034eb7422f4b', hub)
        disconnect.append(other_client)

        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(other_client, other_leaf.uuid, 'other_sensor', False, 'bool')

        predicates = ['=', [rfid_leaf.uuid, 'rfid_reader'], 3032042781]
        await self.send_create_condition(admin_client, admin_leaf.uuid, "invalid_output_condition",
                                         predicates, actions=[self.create_action('SET', other_leaf.uuid, 'other_sensor', action_value=True)])

        response = await admin_client.receive_json_from()
        assert response is not None, "Expected invalid device message as other_sensor is not an output"
        assert response['type'] == 'INVALID_DEVICE'

    async def test_basic_condition(self, disconnect):
        self.create_user_and_client()
        hub = self.create_hub("test_hub")

        name = 'basic-datastore'

        admin_client, admin_leaf = await self.send_create_leaf('admin_leaf', '0', '2e11b9fc-5725-4843-8b9c-4caf2d69c499', hub)
        disconnect.append(admin_client)

        rfid_client, rfid_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub)
        disconnect.append(rfid_client)

        await self.send_create_datastore(rfid_client, rfid_leaf.uuid, 'door_open', False, 'bool')
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 301323, 'number')

        predicates = ['=', [rfid_leaf.uuid, 'rfid_reader'], 33790]
        await self.send_create_condition(admin_client, admin_leaf.uuid, name,
                                         predicates, actions=[self.create_action('SET', 'datastore', 'door_open', action_value=True)])

        door_open = Datastore.objects.get(name="door_open")

        assert door_open.value == False, \
                         'The RFID leaf does not meet the predicate, so the datastore should be false'
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 0, 'number')

        door_open.refresh_from_db()
        assert door_open.value == False, \
                         'The RFID leaf does not meet the predicate, so the datastore should be false'
        
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 33790, 'number')
        await rfid_client.receive_nothing()
        door_open.refresh_from_db()
        
        assert door_open.value == True, \
                         'The RFID leaf does meet the predicate, so the datastore should be true'
        
        await self.send_device_update(rfid_client, rfid_leaf.uuid, 'rfid_reader', 0, 'number')
        await rfid_client.receive_nothing()
        door_open.refresh_from_db()
        
        assert door_open.value == True, \
                         'The datastore should not update to false if the predicate is no longer true'

        await self.send_delete_condition(admin_client, admin_leaf.uuid, name)

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestHubs(ConsumerTests):
    async def test_multiple_hubs_leaves(self):
        self.create_user_and_client()
        hub1 = self.create_hub("first_hub")
        hub2 = self.create_hub("second_hub")
        hub1_client, hub1_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub1)
        hub2_client, hub2_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub2)

        assert hub2.leaves.count() == 1
        assert hub1.leaves.count() == 1

        await self.send_device_update(hub1_client, hub1_leaf.uuid, 'rfid', 323, 'number')
        assert await hub1_client.receive_nothing(), "Expected no response from both on device creation"
        assert await hub2_client.receive_nothing(), "Expected no response from both on device creation"

        assert hub2_leaf.devices.count() == 0
        assert hub1_leaf.devices.count() == 1

    async def test_multiple_hubs_subscriptions(self):
        self.create_user_and_client()
        hub1 = self.create_hub("first_hub")
        hub2 = self.create_hub("second_hub")
        hub1_client, hub1_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub1)
        hub2_client, hub2_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub2)
        observer_client, observer_leaf = await self.send_create_leaf('rfid_leaf', '0',
                                                               'cd1b7879-d17a-47e5-bc14-26b3fc554e49', hub1)
        # set initial values
        await self.send_device_update(hub1_client, hub1_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(hub2_client, hub2_leaf.uuid, 'rfid_reader', 33790, 'number')

        # subscribe
        await self.send_subscribe(observer_client, observer_leaf.uuid, hub1_leaf.uuid, 'rfid_reader')

        # update rfid device
        await self.send_device_update(hub1_client, hub1_leaf.uuid, 'rfid_reader', 3032042781, 'number')
        assert await hub1_client.receive_nothing(), "Didn't  expect a response"
        assert await hub2_client.receive_nothing(), "Didn't  expect a response"

        # test that subscription message was received and check parameters
        sub_message = await observer_client.receive_json_from()
        assert sub_message is not None, "Expected to receive a subscription update"
        assert sub_message['type'] == 'SUBSCRIPTION_UPDATE', "Expected message to be a subscription update"

        # make sure other device doesn't trigger subscription event
        await self.send_device_update(hub2_client, hub2_leaf.uuid, 'rfid_reader', 3230, 'number')
        assert await observer_client.receive_nothing(), "Didn't  expect a response"
        assert await hub1_client.receive_nothing(), "Didn't  expect a response"
        assert await hub2_client.receive_nothing(), "Didn't  expect a response"

    async def test_multiple_hubs_conditions(self):
        self.create_user_and_client()
        hub1 = self.create_hub("first_hub")
        hub2 = self.create_hub("second_hub")
        hub1_client, hub1_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub1)
        out_client1, out_leaf1 = await self.send_create_leaf('rfid_leaf', '0', '7cfb0bde-7b0e-430b-a033-034eb7422f4b', hub1)
        hub2_client, hub2_leaf = await self.send_create_leaf('rfid_leaf', '0', 'a581b491-da64-4895-9bb6-5f8d76ebd44e', hub2)
        out_client2, out_leaf2 = await self.send_create_leaf('rfid_leaf', '0', '7cfb0bde-7b0e-430b-a033-034eb7422f4b', hub2)

        await self.send_device_update(hub1_client, hub1_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(hub2_client, hub2_leaf.uuid, 'rfid_reader', 33790, 'number')
        await self.send_device_update(out_client1, out_leaf1.uuid, 'output', False, 'bool', mode="OUT")
        await self.send_device_update(out_client2, out_leaf2.uuid, 'output', False, 'bool', mode="OUT")

        predicate = ['=', [hub1_leaf.uuid, 'rfid_reader'], 3032042781]
        await self.send_create_condition(hub1_client, hub1_leaf.uuid, "multi_condition",
                                         predicate, actions=[self.create_action('SET', out_leaf1.uuid,
                                                             'output', action_value=True)])

        # send value that would satisfy predicate from wrong hub
        await self.send_device_update(hub2_client, hub2_leaf.uuid, 'rfid_reader', 3032042781, 'number')

        # ensure no response was received by either output device
        assert await out_client1.receive_nothing(), "Leaf from wrong hub satisfied predicate"
        assert await out_client2.receive_nothing(), "Condition created on wrong hub"

        # satisfy predicate from correct hub
        await self.send_device_update(hub1_client, hub1_leaf.uuid, 'rfid_reader', 3032042781, 'number')

        # ensure that only one hub receives output
        assert await out_client1.receive_json_from(), "Expected an out on hub1"
        assert await out_client2.receive_nothing(), "Did not expect second hub to receive output"
