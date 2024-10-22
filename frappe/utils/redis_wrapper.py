# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
import pickle
import re

import redis
from redis.commands.search import Search

import frappe
from frappe.utils import cstr


class RedisearchWrapper(Search):
	def sugadd(self, key, *suggestions, **kwargs):
		return super().sugadd(self.client.make_key(key), *suggestions, **kwargs)

	def suglen(self, key):
		return super().suglen(self.client.make_key(key))

	def sugdel(self, key, string):
		return super().sugdel(self.client.make_key(key), string)

	def sugget(self, key, *args, **kwargs):
		return super().sugget(self.client.make_key(key), *args, **kwargs)


class RedisWrapper(redis.Redis):
	"""Redis client that will automatically prefix conf.db_name"""

	def connected(self):
		try:
			self.ping()
			return True
		except redis.exceptions.ConnectionError:
			return False

	def __call__(self):
		"""WARNING: Added for backward compatibility to support frappe.cache().method(...)"""
		return self

	def make_key(self, key, user=None, shared=False):
		if shared:
			return key
		if user:
			if user is True:
				user = frappe.session.user

			key = f"user:{user}:{key}"

		return f"{frappe.conf.db_name}|{key}".encode()

	def set_value(self, key, val, user=None, expires_in_sec=None, shared=False):
		"""Sets cache value.

		:param key: Cache key
		:param val: Value to be cached
		:param user: Prepends key with User
		:param expires_in_sec: Expire value of this key in X seconds
		"""
		key = self.make_key(key, user, shared)

		if not expires_in_sec:
			frappe.local.cache[key] = val

		try:
			if expires_in_sec:
				self.setex(name=key, time=expires_in_sec, value=pickle.dumps(val))
			else:
				self.set(key, pickle.dumps(val))

		except redis.exceptions.ConnectionError:
			return None

	def get_value(self, key, generator=None, user=None, expires=False, shared=False):
		"""Returns cache value. If not found and generator function is
		        given, it will call the generator.

		:param key: Cache key.
		:param generator: Function to be called to generate a value if `None` is returned.
		:param expires: If the key is supposed to be with an expiry, don't store it in frappe.local
		"""
		original_key = key
		key = self.make_key(key, user, shared)

		if key in frappe.local.cache:
			val = frappe.local.cache[key]

		else:
			val = None
			try:
				val = self.get(key)
			except redis.exceptions.ConnectionError:
				pass

			if val is not None:
				val = pickle.loads(val)

			if not expires:
				if val is None and generator:
					val = generator()
					self.set_value(original_key, val, user=user)

				else:
					frappe.local.cache[key] = val

		return val

	def get_all(self, key):
		ret = {}
		for k in self.get_keys(key):
			ret[key] = self.get_value(k)

		return ret

	def get_keys(self, key):
		"""Return keys starting with `key`."""
		try:
			key = self.make_key(key + "*")
			return self.keys(key)

		except redis.exceptions.ConnectionError:
			regex = re.compile(cstr(key).replace("|", r"\|").replace("*", r"[\w]*"))
			return [k for k in list(frappe.local.cache) if regex.match(cstr(k))]

	def delete_keys(self, key):
		"""Delete keys with wildcard `*`."""
		self.delete_value(self.get_keys(key), make_keys=False)

	def delete_key(self, *args, **kwargs):
		self.delete_value(*args, **kwargs)

	def delete_value(self, keys, user=None, make_keys=True, shared=False):
		"""Delete value, list of values."""
		if not keys:
			return

		if not isinstance(keys, list | tuple):
			keys = (keys,)

		if make_keys:
			keys = [self.make_key(k, shared=shared, user=user) for k in keys]

		for key in keys:
			frappe.local.cache.pop(key, None)

		try:
			self.delete(*keys)
		except redis.exceptions.ConnectionError:
			pass

	def lpush(self, key, value):
		return super().lpush(self.make_key(key), value)

	def rpush(self, key, value):
		return super().rpush(self.make_key(key), value)

	def lpop(self, key):
		return super().lpop(self.make_key(key))

	def rpop(self, key):
		return super().rpop(self.make_key(key))

	def llen(self, key):
		return super().llen(self.make_key(key))

	def lrange(self, key, start, stop):
		return super().lrange(self.make_key(key), start, stop)

	def ltrim(self, key, start, stop):
		return super().ltrim(self.make_key(key), start, stop)

	def hset(
		self,
		name: str,
		key: str,
		value,
		shared: bool = False,
		*args,
		**kwargs,
	):
		if key is None:
			return

		_name = self.make_key(name, shared=shared)

		# set in local
		frappe.local.cache.setdefault(_name, {})[key] = value

		# set in redis
		try:
			super().hset(_name, key, pickle.dumps(value), *args, **kwargs)
		except redis.exceptions.ConnectionError:
			pass

	def hexists(self, name: str, key: str, shared: bool = False) -> bool:
		if key is None:
			return False
		_name = self.make_key(name, shared=shared)
		try:
			return super().hexists(_name, key)
		except redis.exceptions.ConnectionError:
			return False

	def exists(self, *names: str, user=None, shared=None) -> int:
		names = [self.make_key(n, user=user, shared=shared) for n in names]

		try:
			return super().exists(*names)
		except redis.exceptions.ConnectionError:
			return False

	def hgetall(self, name):
		value = super().hgetall(self.make_key(name))
		return {key: pickle.loads(value) for key, value in value.items()}

	def hget(self, name, key, generator=None, shared=False):
		_name = self.make_key(name, shared=shared)
		if _name not in frappe.local.cache:
			frappe.local.cache[_name] = {}

		if not key:
			return None

		if key in frappe.local.cache[_name]:
			return frappe.local.cache[_name][key]

		value = None
		try:
			value = super().hget(_name, key)
		except redis.exceptions.ConnectionError:
			pass

		if value is not None:
			value = pickle.loads(value)
			frappe.local.cache[_name][key] = value
		elif generator:
			value = generator()
			self.hset(name, key, value, shared=shared)
		return value

	def hdel(self, name, key, shared=False):
		_name = self.make_key(name, shared=shared)

		if _name in frappe.local.cache:
			if key in frappe.local.cache[_name]:
				del frappe.local.cache[_name][key]
		try:
			super().hdel(_name, key)
		except redis.exceptions.ConnectionError:
			pass

	def hdel_keys(self, name_starts_with, key):
		"""Delete hash names with wildcard `*` and key"""
		for name in self.get_keys(name_starts_with):
			name = name.split("|", 1)[1]
			self.hdel(name, key)

	def hkeys(self, name):
		try:
			return super().hkeys(self.make_key(name))
		except redis.exceptions.ConnectionError:
			return []

	def sadd(self, name, *values):
		"""Add a member/members to a given set"""
		super().sadd(self.make_key(name), *values)

	def srem(self, name, *values):
		"""Remove a specific member/list of members from the set"""
		super().srem(self.make_key(name), *values)

	def sismember(self, name, value):
		"""Returns True or False based on if a given value is present in the set"""
		return super().sismember(self.make_key(name), value)

	def spop(self, name):
		"""Removes and returns a random member from the set"""
		return super().spop(self.make_key(name))

	def srandmember(self, name, count=None):
		"""Returns a random member from the set"""
		return super().srandmember(self.make_key(name))

	def smembers(self, name):
		"""Return all members of the set"""
		return super().smembers(self.make_key(name))

	def ft(self, index_name="idx"):
		return RedisearchWrapper(client=self, index_name=self.make_key(index_name))


def setup_cache():
	if frappe.conf.redis_cache_sentinel_enabled:
		sentinels = [tuple(node.split(":")) for node in frappe.conf.get("redis_cache_sentinels", [])]
		sentinel = get_sentinel_connection(
			sentinels=sentinels,
			sentinel_username=frappe.conf.get("redis_cache_sentinel_username"),
			sentinel_password=frappe.conf.get("redis_cache_sentinel_password"),
			master_username=frappe.conf.get("redis_cache_master_username"),
			master_password=frappe.conf.get("redis_cache_master_password"),
		)
		return sentinel.master_for(
			frappe.conf.get("redis_cache_master_service"),
			redis_class=RedisWrapper,
		)

	return RedisWrapper.from_url(frappe.conf.get("redis_cache"))


def get_sentinel_connection(
	sentinels: list[tuple[str, int]],
	sentinel_username=None,
	sentinel_password=None,
	master_username=None,
	master_password=None,
):
	from redis.sentinel import Sentinel

	sentinel_kwargs = {}
	if sentinel_username:
		sentinel_kwargs["username"] = sentinel_username

	if sentinel_password:
		sentinel_kwargs["password"] = sentinel_password

	return Sentinel(
		sentinels=sentinels,
		sentinel_kwargs=sentinel_kwargs,
		username=master_username,
		password=master_password,
	)
