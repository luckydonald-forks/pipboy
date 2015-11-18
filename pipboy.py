#!/usr/bin/env python

import struct

import socket
import json
import StringIO
import threading

import logging
import pprint
pp = pprint.PrettyPrinter()

TCP_PORT = 27000
UDP_PORT = 28000

class TCPFormat(object):
    logger = logging.getLogger("pipboy.TCPFormat")
    @staticmethod
    def __load_bool(stream):
	(val,) = struct.unpack('<B', stream.read(1))
	val = [False,True][val]
	return val

    @staticmethod
    def __load_native( stream, size, unpack ):
	(val,) = struct.unpack(unpack, stream.read(size))
	return val

    @staticmethod
    def __load_cstr( stream ):
	buffer = bytearray()
	while True:
	    byte = stream.read(1)
	    if byte == '\x00':
		return str(buffer)
	    else:
		buffer.append(byte)

    @staticmethod
    def __load_list( stream):
	value = []
	(_count,) = struct.unpack('<H', stream.read(2))
	for i in range(0,_count):
	    (tmp,) = struct.unpack('<I', stream.read(4))
	    value.append(tmp)
	return value

    @staticmethod
    def __load_dict( stream):
	value = {}
	(_count,) = struct.unpack('<H', stream.read(2))
	for i in range(0,_count):
	    (ref,) = struct.unpack('<I', stream.read(4))
	    attribute = TCPFormat.__load_cstr(stream)
	    value[attribute] = ref
	(_unknown,) = struct.unpack('<H', stream.read(2))
	return value

    @staticmethod
    def load(stream):
	items = []
	while True:
	    typ = stream.read(1)
	    if not typ: break
	    (typ,) = struct.unpack('<B', typ)
	    (_id,) = struct.unpack('<I', stream.read(4))
	    if typ == 0: # confirmed bool
		value = TCPFormat.__load_bool(stream)
	    elif typ == 1:
		value = TCPFormat.__load_native(stream, 1, '<b')
	    elif typ == 2:
		value = TCPFormat.__load_native(stream, 1, '<B')
	    elif typ == 3:
		value = TCPFormat.__load_native(stream, 4, '<i')
	    elif typ == 4: # confirmed uint_32
		value = TCPFormat.__load_native(stream, 4, '<I')
	    elif typ == 5: # confirmed float
		value = TCPFormat.__load_native(stream, 4, '<f')
	    elif typ == 6:
		value = TCPFormat.__load_cstr(stream)
	    elif typ == 7:
		value = TCPFormat.__load_list(stream)
	    elif typ == 8:
		value = TCPFormat.__load_dict(stream)
	    else:
		TCPFormat.logger.error("Unknown Typ %d" % typ)
		break
	    items.append( [ _id, value ] )
	return items

    @staticmethod
    def __dump_cstr( stream, string ):
	stream.write(string)
	stream.write('\x00')

    @staticmethod
    def __dump_head( stream, _id, typ):
	stream.write(struct.pack('<BI', typ, _id))

    @staticmethod
    def __dump( stream, _id, typ, value ):
	TCPFormat.__dump_head(stream,_id, typ)
	stream.write(value)

    @staticmethod
    def __dump_pack( stream, _id, typ, pack, value ):
	TCPFormat.__dump( stream, _id, typ, struct.pack( pack, value))

    @staticmethod
    def __dump_bool( stream, _id, item ):
	TCPFormat.__dump_pack ( stream, _id, 0, '<B', 1 if item else 0 )

    @staticmethod
    def __dump_int( stream, _id, item ):
	if item < 0:
	    if item < -128:
		typ = ( 3, '<i')
	    else:
		typ = ( 1, '<b')
	else:
	    if item > 127:
		typ = ( 4, '<I')
	    else:
		typ = ( 2, '<b')
	TCPFormat.__dump_pack( stream, _id, typ[0], typ[1], item)

    @staticmethod
    def __dump_float( stream, _id, item ):
	TCPFormat.__dump_pack ( stream, _id, 5, '<f', item )

    @staticmethod
    def __dump_str( stream, _id, item ):
	TCPFormat.__dump_head(stream, _id, 6)
	TCPFormat.__dump_cstr(stream, item)

    @staticmethod
    def __dump_list( stream, _id, item ):
	TCPFormat.__dump_head(stream, _id, 7)
	stream.write(struct.pack('<H', len(item) ))
	for val in item:
	    stream.write(struct.pack('<I', val))

    @staticmethod
    def __dump_dict( stream, _id, item ):
	TCPFormat.__dump_head(stream, _id, 8)
	stream.write(struct.pack('<H', len(item) ))
	for key, val in item.items():
	    stream.write(struct.pack('<I', val))
	    TCPFormat.__dump_cstr(stream, key)
	stream.write(struct.pack('<H', 0 ))

    @staticmethod
    def dump( items, stream):
	for _id, value in items:
	    if type(value) == bool:
		TCPFormat.__dump_bool(stream, _id, value)
	    elif type(value) == int:
		TCPFormat.__dump_int(stream, _id, value)
	    elif type(value) == float:
		TCPFormat.__dump_float(stream, _id, value)
	    elif type(value) == str:
		TCPFormat.__dump_str(stream, _id, value)
	    elif type(value) == list:
		TCPFormat.__dump_list(stream, _id, value)
	    elif type(value) == dict:
		TCPFormat.__dump_dict(stream, _id, value)

class AppFormat(object):
    logger = logging.getLogger("pipboy.AppFormat")

    spelling = ['ActiveEffects', 'BodyFlags', 'Caps', 'ClearedStatus',
		'Clip', 'CurrAP', 'CurrCell', 'CurrHP', 'CurrWeight',
		'CurrWorldspace', 'CurrentHPGain', 'Custom', 'DateDay',
		'DateMonth', 'DateYear', 'Description', 'Discovered',
		'Doors', 'EffectColor', 'Extents', 'FavIconType', 'HandleID',
		'HeadCondition', 'HeadFlags', 'Height', 'HolotapePlaying',
		'InvComponents', 'Inventory', 'IsDataUnavailable',
		'IsInAnimation', 'IsInAutoVanity', 'IsInVats',
		'IsInVatsPlayback', 'IsLoading', 'IsMenuOpen',
		'IsPipboyNotEquipped', 'IsPlayerDead', 'IsPlayerInDialogue',
		'IsPlayerMovementLocked', 'IsPlayerPipboyLocked',
		'LArmCondition', 'LLegCondition', 'ListVisible',
		'Local', 'LocationFormId', 'LocationMarkerFormId',
		'Locations', 'Log', 'Map', 'MaxAP', 'MaxHP', 'MaxRank',
		'MaxWeight', 'MinigameFormIds', 'Modifier', 'NEX', 'NEY',
		'NWX', 'NWY', 'Name', 'OnDoor', 'PaperdollSection',
		'PerkPoints', 'Perks', 'Player', 'PlayerInfo',
		'PlayerName', 'PowerArmor', 'QuestId', 'Quests',
		'RArmCondition', 'RLegCondition', 'RadawayCount',
		'Radio', 'Rank', 'Rotation', 'SWFFile', 'SWX', 'SWY',
		'Shared', 'SlotResists', 'SortMode', 'Special', 'StackID',
		'Stats', 'Status', 'StimpakCount', 'TimeHour', 'TorsoCondition',
		'TotalDamages', 'TotalResists', 'UnderwearType', 'Value',
		'ValueType', 'Version', 'Visible', 'Workshop',
		'WorkshopHappinessPct', 'WorkshopOwned', 'WorkshopPopulation',
		'World', 'X', 'XPLevel', 'XPProgressPct', 'Y',
		'canFavorite', 'damageType', 'diffRating', 'equipState',
		'filterFlag', 'formID', 'inRange', 'isLegendary',
		'isPowerArmorItem', 'itemCardInfoList', 'mapMarkerID',
		'radawayObjectID', 'radawayObjectIDIsValid',
		'scaleWithDuration', 'showAsPercent', 'showIfZero',
		'sortedIDS', 'statArray', 'stimpakObjectID',
		'stimpakObjectIDIsValid', 'taggedForSearch', 'workshopData']

    @staticmethod
    def __load_string(stream):
	(size,) = struct.unpack('<I', stream.read(4))
	return stream.read(size)

    @staticmethod
    def __load_native(stream):
	(typ,) = struct.unpack('<B', stream.read(1))
	if typ == 2:
	    (value,) = struct.unpack('<q', stream.read(8))
	elif typ == 4:
	    (value,) = struct.unpack('<d', stream.read(8))
	elif typ == 5:
	    (value,) = struct.unpack('<B', stream.read(1))
	    value = [False,True][value]
	elif typ == 6:
	    value = AppFormat.__load_string( stream)
	else:
	    AppFormat.logger.error("Unknown Native Typ %d" % typ)
	return value

    @staticmethod
    def __load_list(stream):
	children = []
	(_count,) = struct.unpack('<I', stream.read(4))
	value = [None] * _count
	for i in range(0, _count):
	    (_index,) = struct.unpack('<I', stream.read(4))
	    (_id, child) = AppFormat.__load_type(stream)
	    value[_index] = _id
	    children += child
	return (value, children)

    @staticmethod
    def __load_dict(stream):
	children = []
	(_count,) = struct.unpack('<I', stream.read(4))
	value = {}
	for i in range(0, _count):
	    name = AppFormat.__load_string(stream)
	    for x in AppFormat.spelling:
		if x.lower() == name.lower():
		    name = x
		    break
	    (_id, child) = AppFormat.__load_type(stream)
	    value[name] = _id
	    children += child
	return (value, children)

    @staticmethod
    def __load_type(stream):
	(typ,_id) = struct.unpack('<BI', stream.read(5))
	if typ == 0:
	    value = AppFormat.__load_native(stream)
	    children = []
	elif typ == 1:
	    (value, children) = AppFormat.__load_list(stream)
	elif typ == 2:
	    (value, children) = AppFormat.__load_dict(stream)
	else:
	    AppFormat.logger.error("Unknown Typ %d" % typ)
	children.append([_id,value])
	return (_id, children )

    @staticmethod
    def load(stream):
	(_,result) = AppFormat.__load_type(stream)
	return result

class BuiltinFormat(object):
    logger = logging.getLogger("pipboy.BuiltinFormat")

    @staticmethod
    def __load_list(item, _id):
	value = []
	children = []
	next_id = _id + 1
	for subitem in item:
	    value.append( next_id )
	    ( next_id, child ) = BuiltinFormat.__load( subitem, next_id)
	    children += child
	children.append( [ _id, value ] )
	return ( next_id, children )

    @staticmethod
    def __load_dict(item, _id):
	value = {}
	children = []
	next_id = _id + 1
	for name, subitem in item.items():
	    value[name] = next_id
	    ( next_id, child ) = BuiltinFormat.__load( subitem, next_id)
	    children += child
	children.append( [ _id, value ] )
	return ( next_id, children )

    @staticmethod
    def __load(item, _id):
	if type(item) == dict:
	    return BuiltinFormat.__load_dict( item, _id)
	elif type(item) == list:
	    return BuiltinFormat.__load_list( item, _id)
	else:
	    return ( _id + 1, [[ _id, item ] ])

    @staticmethod
    def load(item):
	(_,result) = BuiltinFormat.__load(item, 0)
	return result

    @staticmethod
    def __dump_model(model, _id):
	result = model.get_items(_id)
	if type(result) == list:
	    result = [ BuiltinFormat.__dump_model(model,v) for v in result ]
	elif type(result) == dict:
	    result = { k: BuiltinFormat.__dump_model(model,v) for k, v in result.items() }
	return result

    @staticmethod
    def dump_model(model):
	return BuiltinFormat.__dump_model(model,0)

class Model(object):
    logger = logging.getLogger('pipboy.Model')

    __startup = {
	    'Inventory': {},
	    "Log": [],
	    "Map": {},
	    "Perks": [],
	    "PlayerInfo": {},
	    "Quests": [],
	    "Radio": [],
	    "Special": [],
	    "Stats": {},
	    "Status": {
		"EffectColor": [
		    0.08,
		    1.0,
		    0.09
		],
		"IsDataUnavailable": True,
		"IsInAnimation": False,
		"IsInAutoVanity": False,
		"IsInVats": False,
		"IsInVatsPlayback": False,
		"IsLoading": False,
		"IsMenuOpen": False,
		"IsPipboyNotEquipped": True,
		"IsPlayerDead": False,
		"IsPlayerInDialogue": False,
		"IsPlayerMovementLocked": False,
		"IsPlayerPipboyLocked": False
	    },
	    "Workshop": []
	}

    def __clear(self):
	self.__path = {}
	self.__items = {}

    def __init__( self ):
	super(Model, self).__init__()
	self.listener = { 'update': [], 'command': [] }
	self.load(BuiltinFormat.load( Model.__startup))

    def register( self, typ, function):
	self.listener[typ].append( function)

    def get_item( self, _id ):
	return self.__items[_id]

    def get_path( self, _id ):
	if _id == 0:
	    return "$"
	else:
	    (name, parent) = self.__path[_id]
	    return self.get_path(parent) + name

    def update( self, items):
	changed = []
	for _id, value in items:
	    self.__items[_id] = value
	    changed.append(_id)
	    if type(value) == list:
		for k, v in enumerate(value):
		    self.__path[v] = ( "[%d]" % k, _id )
	    elif type(value) == dict:
		for k, v in value.items():
		    self.__path[v] = ( ".%s" % k, _id )
	for func in self.listener['update']:
	    func(changed)

    def load( self, items):
	self.__clear()
	self.update(items)

    def dump( self, _id = 0, recursive = False):
	item = self.__items[_id]
	result = []
	if recursive:
	    if type(item) == list:
		for child in item:
		    result += self.dump( child, recursive)
	    elif type(item) == dict:
		for child in item.values():
		    result += self.dump( child, recursive)
	result.append([ _id, item])
	return result

class PipBoy(object):
    def _clear(self):
	self._path = {}
	self._items = {}

    def __init__( self ):
	self.logger = logging.getLogger('pipboy.PipBoy')
	self._clear()


    def _convert_str(self, string):
	if type(string) == unicode:
	    return string.encode('utf8')
	else:
	    return string

    def _load_type(self, item ):
	_id = len(self._items)
	self._items[_id] = item
	self._convert_str(item)
	if type(item) == unicode:
	    self._items[_id] = item.encode('utf8')
	elif type(item) == list:
	    self._items[_id] = [ self._load_type(child) for child in item ]
	elif type(item) == dict:
	    self._items[_id] = { self._convert_str(k): self._load_type(v) for k,v in item.items() }
	return _id

    def load_type( self, item ):
	self._clear()
	self._load_type( item )
	inventory = self._items[0]['Inventory']
	inventory = self._items[inventory]
	sorted_ids = inventory['sortedIDS']
	sorted_ids = self._items[sorted_ids]
	print "START"
	print len(sorted_ids)
	all_ids = []
	for k,v in inventory.items():
	    tmp = self._items[v]
	    if k.isdigit():
		all_ids += tmp
		print len(tmp)
	sorted_i = []
	for i in all_ids:
	    _id = len(self._items)
	    self._items[_id] = i
	    sorted_i.append(_id)
	sorted_ids = inventory['sortedIDS']
	self._items[sorted_ids] = sorted_i
	print "DONE"

class UDPClient(object):
    @staticmethod
    def discover():
	udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
	udp_socket.settimeout(5)
	udp_socket.sendto(json.dumps({'cmd': 'autodiscover'}), ('<broadcast>', UDP_PORT))
	result = []
	timeout = False
	while not timeout:
	    try:
		received, fromaddr = udp_socket.recvfrom(1024)
		data = json.loads(received)
		data['IpAddr'] = fromaddr[0]
		result.append(data)
	    except socket.timeout, e:
		timeout = True
	return result

class TCPBase(object):
    def __init__( self, model):
	super(TCPBase, self).__init__()
	self.logger = logging.getLogger('pipboy.TCPBase')
	self.socket = None
	self.model = model

    def receive(self):
	header = self.socket.recv(5)
	size, channel = struct.unpack('<IB', header)
	data = ''
	while size > 0:
	    tmp = self.socket.recv(size)
	    data += tmp
	    size -= len(tmp)
	return ( channel, data )

    def send(self, channel, data):
	header = struct.pack('<IB', len(data), channel)
	self.socket.send(header)
	self.socket.send(data)

    serve = False
    thread = None

    def start(self):
	self.thread = threading.Thread(target=self.__run, name=type(self).__name__)
	self.thread.daemon = True
	self.thread.start()
    
    def pre():
	pass

    def run():
	pass

    def post():
	if socket:
	    socket.close()

    def __run(self):
	self.pre()
	self.serve = True
	while self.serve:
	    self.run()
	self.post()

    def stop(self):
	self.serve = False
	thread.join()

class TCPClient(TCPBase):
    def __init__( self, model = Model() ):
	super(TCPClient, self).__init__(model)
	self.logger = logging.getLogger('pipboy.TCPClient')

    server = None

    def pre(self):
	self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	self.socket.connect((self.server, TCP_PORT))

    def run(self):
	(channel, data) = self.receive()
	if channel == 0:
	    pass
	elif channel == 1:
	    pass
	elif channel == 3:
	    stream = StringIO.StringIO(data)
	    self.model.update(TCPFormat.load(stream))
	else:
	    self.logger.warn("Error Unknown Channel %d" % ( channel))
	self.send( 0, '')

class TCPServer(TCPBase):
    def __init__( self, model = Model() ):
	super(TCPServer, self).__init__(model)
	self.logger = logging.getLogger('pipboy.TCPServer')
	self.model.register('update',self.listen_update)

    server = None

    def __send_updates(self, items):
	stream = StringIO.StringIO()
	TCPFormat.dump( items, stream)
	self.send( 3, stream.getvalue())

    def listen_update(self, items):
	if self.socket:
	    updates = []
	    for item in items:
		updates += self.model.dump( item, False)
	    self.__send_updates( updates)

    def pre(self):
	self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	self.server.bind(('', TCP_PORT))
	self.server.listen(1)
	connection, addr = self.server.accept()
	self.socket = connection
	self.send( 1, json.dumps( { 'lang': 'de', 'version': '1.1.30.0' }))
	self.__send_updates( self.model.dump(0,True))

    def run(self):
	(channel, data) = self.receive()
	if channel == 0:
	    pass
	elif channel == 1:
		    self.logger.debug(json.loads(data))
	elif channel == 3:
	    stream = StringIO.StringIO(data)
	    self.model.update(TCPFormat.load(stream))
	elif channel == 5:
	    self.logger.debug(json.loads(data))
	else:
	    self.logger.warn("Error Unknown Channel %d" % ( channel))
	self.send( 0, '')

