from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from polymorphic.models import PolymorphicModel
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from types import SimpleNamespace
import logging
import json

logger = logging.getLogger(__name__)

class Value(PolymorphicModel):
    value = None
    format = None

    def __repr__(self):
        return str(self.value)

    def __str__(self):
        return repr(self)

    def to_json(self):
        if self.format in ['number', 'number+units']:
            return float(self.value)
        else:
            return self.value


class StringValue(Value):
    value = models.CharField(max_length=250)

    @property
    def format(self):
        return "string"


class NumberValue(Value):
    value = models.DecimalField(max_digits=15, decimal_places=4)

    @property
    def format(self):
        return "number"


class UnitValue(Value):
    value = models.DecimalField(max_digits=15, decimal_places=4)
    units = models.CharField(max_length=10)

    @property
    def format(self):
        return "number+units"

    def __repr__(self):
        return "{}{}".format(self.value, self.units)


class BooleanValue(Value):
    value = models.BooleanField()

    @property
    def format(self):
        return "bool"


class Hub(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return f"{self.name} - {self.id}"

    def get_device(self, uuid, device):
        from .utils import InvalidLeaf, InvalidDevice
        try:
            if uuid == 'datastore':
                return self.datastores.get(name=device)
            else:
                return self.leaves.get(uuid=uuid).get_device(device, False)
        except Leaf.DoesNotExist:
            raise InvalidLeaf(uuid)
        except Datastore.DoesNotExist:
            raise InvalidDevice(SimpleNamespace(uuid='datastore'), SimpleNamespace(name=device), InvalidDevice.UNKNOWN)
        except Device.DoesNotExist:
            raise InvalidDevice(self.leaves.get(uuid=uuid), SimpleNamespace(name=device), InvalidDevice.UNKNOWN)

    def get_leaf(self, uuid: str) -> 'Leaf':
        from .utils import InvalidLeaf
        leaf = self.leaves.filter(uuid=uuid)
        if leaf.exists():
            return leaf.first()
        else:
            raise InvalidLeaf(uuid)


class Leaf(models.Model):
    name = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    uuid = models.CharField(max_length=36)
    api_version = models.CharField(max_length=10, default="0.1.0")
    is_connected = models.BooleanField(default=True)
    last_connected = models.DateTimeField()
    last_updated = models.DateTimeField(default=timezone.now)
    hub = models.ForeignKey(Hub, related_name="leaves", on_delete=models.CASCADE)

    class Meta:
        unique_together = (('uuid', 'hub'),)

    def update_time(self):
        self.last_updated = timezone.now()
        self.save()

    def set_name(self, name: str):
        message = self.message_template
        message["type"] = "SET_NAME"
        message["name"] = name
        self.send_message(message)

    def set_option(self, device: str, option: str, value: str):
        message = self.message_template
        message["type"] = "SET_OPTION"
        message["device"] = device
        message["option"] = option
        message["value"] = value
        self.send_message(message)

    def set_output(self, device: str, value: str):
        message = self.message_template
        message["type"] = "SET_OUTPUT"
        message["device"] = device
        message["value"] = value
        self.send_message(message)

    def get_option(self, device: str, option: str, update=True):
        if update:
            self.refresh_option(device, option)
        # TODO: Replace following code with real code, add option
        return self.get_device(device, update=False).option_set.filter(name=option)

    def get_options(self, device: str, update=True):
        if update:
            self.refresh_options()
        return self.get_device(device, update=False).option_set.all()

    def get_device(self, device: str, update=True) -> 'Device':
        if update:
            self.refresh_device(device)
        return self.devices.get(name=device)

    def get_name(self) -> str:
        return self.name

    def refresh_devices(self):
        message = self.message_template
        message["type"] = "LIST_DEVICES"
        self.send_message(message)

    def refresh_name(self):
        message = self.message_template
        message["type"] = "GET_NAME"
        self.send_message(message)

    def refresh_options(self):
        message = self.message_template
        message["type"] = "LIST_OPTIONS"
        self.send_message(message)

    def refresh_device(self, device: str):
        message = self.message_template
        message["type"] = "GET_DEVICE"
        message["device"] = device
        self.send_message(message)

    def refresh_option(self, device: str, option: str):
        message = self.message_template
        message["type"] = "GET_OPTION"
        message["option"] = option
        message["device"] = device
        self.send_message(message)

    def send_message(self, message: dict) -> None:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"{self.hub.id}-{self.uuid}",
            { "type": "leaf.send", "message": message}
        )
        logger.info(f"{self.hub.id} -- <{self.uuid}> sent: {message}")
        

    def send_subscriber_update(self, device):
        seen_devices = set()
        message = device.status_update_dict

        subscriptions = self.hub.subscriptions.filter(target_uuid=self.uuid)
        for subscription in subscriptions.filter(target_device=device.name):
            seen_devices.add(subscription.subscriber_uuid)
            subscription.handle_update(self.uuid, device.name, message)
        # send messages to whole leaf subscribers
        for subscription in subscriptions.filter(target_device="leaf"):
            if subscription.subscriber_uuid not in seen_devices:
                subscription.handle_update(self.uuid, 'leaf', message)

    def get_user(self):
        return User.objects.get(username=self.username)

    @property
    def username(self):
        return f"{self.hub.id}-{self.uuid}"

    @property
    def message_template(self):
        return {"uuid": self.uuid, "hub_id": self.hub_id}

    def __repr__(self):
        return "Leaf <name: {}, uuid:{}>".format(self.name, self.uuid)

    def __str__(self):
        return repr(self)

    @classmethod
    def create_from_message(cls, message, hub):
        model = message['model']
        name = message['name']
        api = message['api_version']
        uuid = message['uuid']
        leaf = cls(name=name, model=model, uuid=uuid, api_version=api, hub=hub)
        return leaf


class Device(models.Model):
    DeviceModes = (('IN', 'Input'), ('OUT', 'Output'))
    name = models.CharField(max_length=100)
    leaf = models.ForeignKey(Leaf, related_name='devices', on_delete=models.CASCADE)
    is_input = models.BooleanField(default=True)
    _value = models.OneToOneField(Value, on_delete=models.CASCADE, related_name="device")
    mode = models.CharField(choices=DeviceModes, max_length=3)

    class Meta:
        unique_together = (('name', 'leaf'),)

    @property
    def value(self):
        return self._value.value

    @value.setter
    def value(self, new_value):
        if new_value != self.value:
            self._value.value = new_value
            self._value.save()
            self.leaf.send_subscriber_update(self)
            self.leaf.update_time()

    @property
    def status_update_dict(self):
        status_update = {
            'type': 'DEVICE_STATUS',
            'uuid': self.leaf.uuid,
            'device': self.name,
            'value': self.value,
            'format': self.format,
        }
        if self.format == 'units':
            status_update['units'] = self._value.units
        return status_update

    def refresh_from_db(self, using=None, fields=None):
        self._value.refresh_from_db()
        return super().refresh_from_db(using=using, fields=fields)

    @staticmethod
    def create_from_message(message, hub):
        try:
            uuid = message['uuid']
            leaf = hub.leaves.get(uuid=uuid)
        except ObjectDoesNotExist:
            return
        except KeyError:
            return

        is_input = message['mode'].upper() == 'IN'

        format = message['format'].lower()
        if format == 'number':
            value = NumberValue(value=message['value'])
        elif format == 'number+units':
            value = UnitValue(value=message['value'], units=message['units'])
        elif format == 'bool':
            value = BooleanValue(value=message['value'])
        else:
            value = StringValue(value=message['value'])
        value.save()

        device = Device(name=message['device'], _value=value, is_input=is_input, leaf=leaf, mode=message['mode'])
        return device

    @property
    def format(self):
        return self._value.format

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return "<Device name:{}, value: {}>".format(self.name, repr(self.value))


class Subscription(PolymorphicModel):
    subscriber_uuid = models.CharField(max_length=36, blank=True, null=True)
    target_uuid = models.CharField(max_length=36)
    target_device = models.CharField(max_length=100)
    hub = models.ForeignKey(Hub, related_name="subscriptions", on_delete=models.CASCADE)

    def handle_update(self, uuid, device, message):
        sub_message = {'type': 'SUBSCRIPTION_UPDATE',
                       'sub_uuid': uuid,
                       'sub_device': device,
                       'message': message}
        self.hub.get_leaf(self.subscriber_uuid).send_message(sub_message)


class Datastore(models.Model):
    _value = models.OneToOneField(Value, on_delete=models.CASCADE, related_name="datastore")
    name = models.CharField(max_length=100)
    hub = models.ForeignKey(Hub, related_name="datastores", on_delete=models.CASCADE)
    last_updated = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (('name', 'hub'),)

    @property
    def format(self):
        return self._value.format

    @property
    def value(self):
        return self._value.value

    @value.setter
    def value(self, new_value):
        if new_value != self.value:
            self._value.value = new_value
            self._value.save()
            message = {
                'type': 'DEVICE_STATUS',
                'value': self.value,
                'format': self.format,
                'uuid': 'datastore',
                'device': self.name
            }
            subscriptions = self.hub.subscriptions.filter(target_uuid="datastore", target_device=self.name)
            for subscription in subscriptions:
                subscription.handle_update("datastore", self.name, message)
            self.last_updated = timezone.now()
            self.save()

    def refresh_from_db(self, using=None, fields=None):
        self._value.refresh_from_db()
        return super().refresh_from_db(using=using, fields=fields)


class Predicate(PolymorphicModel):
    operator = models.ForeignKey('Multivariate', on_delete=models.CASCADE, related_name="operands", null=True)

    def evaluate(self):
        return True

    def to_representation(self):
        return True


class NOT(Predicate):
    predicate = models.ForeignKey(Predicate, on_delete=models.CASCADE, related_name="not+")

    def evaluate(self):
        return not self.predicate.evaluate()

    def delete(self, *args, **kwargs):
        self.predicate.delete()
        super().delete(*args, **kwargs)

    def to_representation(self):
        return ['NOT', self.predicate.to_representation()]


class Multivariate(Predicate):
    op = "NONE"

    def operation(self, *args):
        return False

    def evaluate(self):
        return self.operation(*self.operands.all())

    def delete(self, *args, **kwargs):
        for operand in self.operands:
            operand.delete()
        super().delete(*args, **kwargs)

    def to_representation(self):
        return [self.op, [operand.to_representation() for operand in self.operands.all()]]


class AND(Multivariate):
    op = "AND"

    def operation(self, *args):
        result = True
        for operand in args:
            result = result and operand.evaluate()
            if not result:  # short circuit
                break
        return result


class OR(Multivariate):
    op = "OR"

    def operation(self, *args):
        result = False
        for operand in args:
            result = result or operand.evaluate()
            if result:  # short circuit
                break
        return result


class XOR(Multivariate):
    op = "XOR"

    def operation(self, *args):
        result = False
        for operand in args:
            result = result ^ operand.evaluate()
        return result


class ComparatorPredicate(Predicate):
    first_value = models.ForeignKey(Value, on_delete=models.CASCADE, related_name="first")
    second_value = models.ForeignKey(Value, on_delete=models.CASCADE, related_name="second")
    op = "NONE"

    def save(self, *args, **kwargs):
        if self.first_value.format != self.second_value.format:
            raise TypeError("Type format mismatch. {} does not equal {}".format(self.first_value.format,
                                                                                self.second_value.format))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        try:
            try:  # see if the value is a literal or device value
                self.second_value.device
            except ObjectDoesNotExist:
                self.second_value.datastore
        except ObjectDoesNotExist:
            self.second_value.delete()  # delete the value if it's a literal
        super().delete(*args, **kwargs)

    def to_representation(self):
        return [self.op, self.get_value_representation(self.first_value),
                self.get_value_representation(self.second_value)]

    @staticmethod
    def get_value_representation(value):
        try:
            try:
                device = value.device
                return [device.leaf.uuid, device.name]
            except ObjectDoesNotExist:
                datastore = value.datastore
                return ['datastore', datastore.name]
        except ObjectDoesNotExist:
            return value.to_json()


class EqualPredicate(ComparatorPredicate):
    op = "="

    def evaluate(self):
        return self.first_value.value == self.second_value.value


class LessThanPredicate(ComparatorPredicate):
    op = "<"

    def evaluate(self):
        return self.first_value.value < self.second_value.value


class GreaterThanPredicate(ComparatorPredicate):
    op = ">"

    def evaluate(self):
        return self.first_value.value > self.second_value.value


class Action(PolymorphicModel):
    target_uuid = models.CharField(max_length=36)
    target_device = models.CharField(max_length=36)
    _value = models.OneToOneField(Value, on_delete=models.CASCADE)
    condition = models.ForeignKey('Condition', on_delete=models.CASCADE, related_name='actions', null=True)

    def run(self):
        pass

    @property
    def action_type(self):
        return "None"

    @property
    def format(self):
        return self._value.format


class SetAction(Action):
    def run(self):
        # TODO: consider approaches to avoiding bypassing write guards on changing datastore value here
        if self.target_uuid != 'datastore':
            message = {'type': 'SET_OUTPUT',
                       'uuid': self.target_uuid,
                       'device': self.target_device,
                       'value': self._value.value,
                       'format': self._value.format}
            self.condition.hub.get_leaf(self.target_uuid).send_message(message)
        else:
            datastore = self.condition.hub.datastores.get(name=self.target_device)
            datastore.value = self._value.value

    @property
    def action_type(self):
        return "SET"


class ChangeAction(Action):
    def run(self):
        if self.target_uuid != 'datastore':
            message = {'type': 'CHANGE_OUTPUT',
                       'uuid': self.target_uuid,
                       'device': self.target_device,
                       'value': self.value.value,
                       'format': self.value.format}
            self.condition.hub.get_leaf(self.target_uuid).send_message(message)
        else:
            datastore = self.condition.hub.datastores.get(name=self.target_device)
            datastore.value = datastore.value + self._value.value
            print("here")

    @property
    def action_type(self):
        return "CHANGE"


class Condition(models.Model):
    name = models.CharField(max_length=100)
    predicate = models.OneToOneField(Predicate, on_delete=models.CASCADE, related_name="condition")
    previously_satisfied = models.BooleanField(default=False)
    hub = models.ForeignKey(Hub, related_name="conditions", on_delete=models.CASCADE)

    class Meta:
        unique_together = (('name', 'hub'),)

    def execute(self):
        pred = self.predicate.evaluate()
        if pred and not self.previously_satisfied:
            for action in self.actions.all():
                action.run()
        self.previously_satisfied = pred
        self.save()


class ConditionalSubscription(Subscription):
    condition = models.ForeignKey(Condition, on_delete=models.CASCADE)

    def handle_update(self, uuid, device, message):
        if message['type'] == 'DEVICE_STATUS':
            self.condition.execute()
