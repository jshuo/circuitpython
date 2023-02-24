
# FreeRTOS states are
#
# Running - Currently executing
# Ready - Ready to run but task of higher or equal priority is currently in Running state
# Blocked - Task is waiting for some event, for example, a delay
#           Other reasons for blocks include waiting for a queue, semaphore, or message.
# Suspended - Task was explicitly suspended and will only be resumed by another task.

# For Blocked states, some condition must be met to unblock.  Is it possible that this
# condition could be represented as a function that is called on the task object, that
# will return True if the condition is met?  This would allow the construction of
# lamba or inner functions, that have built in references to any data required to
# determine whether the unblocking condition is met.

# See https://www.freertos.org/RTOS-task-states.html for state transition graph


# Task states
RUNNING   = 0   # Currently executing on the processor
READY     = 1   # Ready to run but task of higher or equal priority is currently running
BLOCKED   = 2   # Task is waiting for some condition to be met to move to READY state
SUSPENDED = 3   # Task is waiting for some other task to unsuspend
				# Why do we need this, since BLOCKED could be used? Creating an
				# unblocking condition for this would require the API to know
				# that the condition is a suspension, and if it already knows
				# it is a suspension, it can just remove it, instead of running
				# the test function.  Thus there is no point in having a
				# function and we might as well just use a flag, since it is
				# cheaper.


class Task(object):
	_out_messages = []

	def __init__(self, func, priority=255, name=None, notifications=None, mailbox=False):
		self.func = func
		self.priority = priority
		self.name = name

		if notifications != None:
			self.notes = (array.array('b', [0] * notifications),
			              array.array('l', [0] * notifications))

		if mailbox:
			self._in_messages = []

		self.state = READY
		self.ready_conditions = []
		self.thread = None  # This is for the generator object

	# If the thread function is well behaved, this will get the generator
	# for it, then it will start it, it will run its initialization code,
	# and then it will yield.
	def initialize(self):
		self.thread = self.func(self)
		next(self.thread)

	# Run task until next yield
	def run_next(self):
		state_change = next(self.thread)

		if state_change != None:
			self.ready_conditions = state_change
			self.state = BLOCKED

		msgs = Task._out_messages
		Task._out_messages = []

		return msgs


# Notification Functions #
	def wait_for_notification(self, index=0, state=1):
		self.notes[0][index] = 0
		while self.notes[0][index] != state:
			yield False

		while True:
			yield True


	def notify_set_value(self, index=0, state=1, value=0):
		self.notes[0][index] = state
		self.notes[1][index] = value

	def notify_inc_value(self, index=0, state=1, step=1):
		self.notes[0][index] = state
		self.notes[1][index] += step

	def notify_get_value(self, index=0):
		return self.notes[1][index]


	def notify_set_state(self, index=0, state=1):
		self.notes[0][index] = state

	def notify_inc_state(self, index=0, step=1):
		self.notes[0][index] += step

	def notify_get_state(self, index=0):
		return self.notes[0][index]
##########################


# Mailbox functions #
	def send(self, msg):
		Task._out_messages.append(msg)

	def recv(self):
		msgs = self._in_messages
		self._in_messages = []
		return msgs

	def message_count(self):
		return len(self._in_messages)

	def deliver(self, msg):
		self._in_messages.append(msg)
#####################


	def suspend(self):
		self.state = SUSPENDED
		self.ready_conditions = []

	def resume(self):
		self.state = READY
		self.ready_conditions = []

import pyRTOS

# Message Types
QUIT = 0
# 1-127 are reserved for future use
# 128+ may be used for user defined message types


class Message(object):
	def __init__(self, type, source, target, message=None):
		self.type = type
		self.source = source
		self.target = target
		self.message = message


def deliver_messages(messages, tasks):
	for message in messages:
		if type(message.target) == pyRTOS.Task:
			message.target.deliver(message)
		else:
			targets = filter(lambda t: message.target == t.name, tasks)
			try:
				next(targets).deliver(message)
			except StopIteration:
				pass


class MessageQueue(object):
	def __init__(self, capacity=10):
		self.capacity = capacity
		self.buffer = []

	# This is a blocking condition
	def send(self, msg):
		sent = False

		while True:
			if sent:
				yield True
			elif len(self.buffer) < self.capacity:
				self.buffer.append(msg)
				yield True
			else:
				yield False

	def nb_send(self, msg):
		if len(self.buffer) < self.capacity:
			self.buffer.append(msg)
			return True
		else:
			return False


	# This is a blocking condition.
	# out_buffer should be a list
	def recv(self, out_buffer):
		received = False
		while True:
			if received:
				yield True
			elif len(self.buffer) > 0:
				received = True
				out_buffer.append(self.buffer.pop(0))
				yield True
			else:
				yield False

	
	def nb_recv(self):
		if len(self.buffer) > 0:
			return self.buffer.pop(0)
		else:
			return None

import pyRTOS


def default_scheduler(tasks):
		messages = []
		running_task = None

		for task in tasks:
			if task.state == pyRTOS.READY:
				if running_task == None:
					running_task = task
			elif task.state == pyRTOS.BLOCKED:
				if True in map(lambda x: next(x), task.ready_conditions):
					task.state = pyRTOS.READY
					task.ready_conditions = []
					if running_task == None:
						running_task = task
			elif task.state == pyRTOS.RUNNING:
				if (running_task == None) or \
				   (task.priority <= running_task.priority):
					running_task = task
				else:
					task.state = pyRTOS.READY


		if running_task:
			running_task.state = pyRTOS.RUNNING

			try:
				messages = running_task.run_next()
			except StopIteration:
				tasks.remove(running_task)

		return messages

import time

import pyRTOS

version = 0.1


tasks = []
service_routines = []


def add_task(task):
	if task.thread == None:
		task.initialize()

	tasks.append(task) 

	tasks.sort(key=lambda t: t.priority)


def add_service_routine(service_routine):
	service_routines.append(service_routine)


def start(scheduler=None):
	global tasks

	if scheduler == None:
		scheduler = pyRTOS.default_scheduler

	run = True
	while run:
		for service in service_routines:
			service()

		messages = scheduler(tasks)
		pyRTOS.deliver_messages(messages, tasks)

		if len(tasks) == 0:
			run = False



# Task Block Conditions

# Timeout   - Task is delayed for no less than the specified time.
def timeout(seconds):
		start = time.monotonic()

		while True:
			yield time.monotonic() - start >= seconds

def timeout_ns(nanoseconds):
		start = time.monotonic_ns()

		while True:
			yield time.monotonic_ns() - start >= nanoseconds

# Cycle Delay - Task is delayed for no less than the number OS loops specified.
def delay(cycles):
	ttl = cycles
	while True:
		if ttl > 0:
			ttl -= 1
			yield False
		else:
			yield True

# Message   - Task is waiting for a message.
def wait_for_message(self):
	while True:
		yield self.message_count() > 0

# Notification - Task is waiting for a notification
def wait_for_notification(task, index=0, state=1):
	task.notes[0][index] = 0
	while task.notes[0][index] != state:
		yield False

	while True:
		yield True



# API I/O   - I/O done by the pyRTOS API has completed.
#             This blocking should be automatic, but API
#             functions may want to provide a timeout
#             arguement.
# API Defined

# UFunction - A user provided function that returns true
#             or false, allowing for complex, user defined
#             conditions.
#
#             UFunctions must be infinite generators.  They can
#             take take any initial arguments, but they must
#             must yield False if the condition is not met and
#             True if it is.  Arguments may be passed into the
#             generator iterations, but pyRTOS should not be
#             expected to pass arguments in when checking. In
#             most cases, it would probably be better to
#             communicate with Ufunctions through globals.
# User Defined


# Blocking is achieved by yielding with a list argument.  Each time pyRTOS
# tests the task for readiness, it will iterate through the list, running
# each generator function, checking the truth value of its output.  If the
# truth value of any element of the list is true, the task will unblock.
# This allows for conditions to effectively be "ORed" together, such that it
# is trivial to add a timeout to any other condition.  If you need to "AND"
# conditions together, write a UFunction that takes a list of conditions and
# yields the ANDed output of those conditions.



# API Elements

# Mutex with priority inheritance
# (highest priority waiting task gets the lock)
class Mutex(object):
	def __init__(self):
		self.locked = False

	# This returns a task block condition generator.  It should
	# only be called using something like "yield [mutex.lock(self)]"
	# or "yield [mutex.lock(self), timeout(1)]"
	def lock(self, task):
		while True:
			if self.locked == False or self.locked == task:
				self.locked = task
				yield True
			else:
				yield False

	def nb_lock(self, task):
		if self.locked == False or self.locked == task:
			self.locked = task
			return True
		else:
			return False

	def unlock(self):
		self.locked = False


# Mutex with request order priority
# (first-come-first-served priority for waiting tasks)
class BinarySemaphore(object):
	def __init__(self):
		self.wait_queue = []
		self.owner = None
		
	# This returns a task block condition generator
	def lock(self, task):
		self.wait_queue.append(task)

		try:
			while True:
				if self.owner == None and self.wait_queue[0] == task:
					self.owner = self.wait_queue.pop(0)
					yield True
				elif self.owner == self:
					yield True
				else:
					yield False
		finally:
			# If this is combined with other block conditions,
			# for example timeout, and one of those conditions
			# unblocks before this, we need to prevent this
			# from taking the lock and never releasing it.
			if task in self.wait_queue:
				self.wait_queue.remove(task)

	def nb_lock(self, task):
		if self.owner == None or self.owner == task:
			self.owner = task
			return True
		else:
			return False

	def unlock(self):
		self.owner = None



