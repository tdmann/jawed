'''
jawed.py - JODConverter Python Wrapper

Helpful library for use in environments where pyuno is unavailable or painful.

Runs tests when run from command line.

Copyright (c) 2011 Tim Mann

Permission is hereby granted, free of charge, to any person obtaining a 
copy of this software and associated documentation files (the "Software"), 
to deal in the Software without restriction, including without limitation 
the rights to use, copy, modify, merge, publish, distribute, sublicense, 
and/or sell copies of the Software, and to permit persons to whom the 
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in 
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN 
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

import os
import shutil
import subprocess
import errno
import Queue
import threading
import unittest

class Jawed:
	'''
	A singleton allowing conversion job scheduling and execution.

	Conversion example:

	from jawed import Jawed

	# initiate the conversion process
	job_number = Jawed.get_instance().queue_conversion_job('test.odt', 'test.pdf')

	# block until job is finished
	result = Jawed.get_instance().wait_for_job(job_number)
	'''


	LAST_SERVED_NONE = -1
	JOB_COMPLETE = -2

	_instance = None

	@staticmethod
	def get_instance():
		if not Jawed._instance:
			Jawed._instance = Jawed()
		return Jawed._instance

	def __init__(self):
		self.jarfile = self.find_jarfile()

		# the queue for all jobs which need to be processed
		self._job_queue = Queue.Queue(0)

		# the dictionary of all finished jobs,
		# keyed by job number
		self._finished_jobs = {}
		self._finished_jobs_lock = threading.Lock()

		# lock to prevent multiple job threads from starting
		self._start_lock = threading.Lock()

		# condition to allow listening for queue updates
		self._update_condition = threading.Condition()

		# the next job number to assign
		self._job_number = 0
		self._last_served = Jawed.LAST_SERVED_NONE
		
		self._thread = None

	def find_jarfile(self):
		'''
		Find the jod jarfile which is being used. Should be located in the same directory as
		this wrapper.
		'''
		folder = '%s/lib' % os.path.split(os.path.abspath(__file__))[0]

		for filename in os.listdir(folder):
			if filename.startswith('jodconverter-core') and filename.endswith('.jar'):
				return '%s/%s' % (folder, filename)
		raise IOError((errno.ENOENT, os.strerror(errno.ENOENT), 'jodconverterlib*.jar'))

	def queue_conversion_job(self, in_filename, out_filename):
		'''
		Places a conversion job in the queue.

		Returns a job number which is used to track the conversion.
		'''
		job_number = self._get_new_job_number()
		if not os.path.exists(in_filename):
			raise IOError((errno.ENOENT, os.strerror(errno.ENOENT), in_filename))
		self._job_queue.put({'job':job_number, 'in':in_filename, 'out':out_filename})
		self._run_thread()
		return job_number

	def wait_status(self, job_number):
		'''
		If the job is finished, return immediately with Jawed.JOB_COMPLETE.
		Otherwise, wait until the queue shifts, and either return the approximate 
		position in line or Jawed.JOB_COMPLETE, depending on if the job finished.
		'''
		if self._job_finished(job_number):
			return Jawed.JOB_COMPLETE
		
		self._update_condition.acquire()
		self._update_condition.wait()
		if self._job_finished(job_number):
			result = Jawed.JOB_COMPLETE
		else:
			result = job_number - self._last_served
		self._update_condition.release()

		return result

	def wait_for_job(self, job_number):
		'''
		Waits for a job to finish. Removes the job from the 
		finished jobs list when it finishes.
		Takes a job number returned from queue_conversion_job.
		'''
		self._update_condition.acquire()
		while not self._job_finished(job_number):
			self._update_condition.wait()
		finished = self.yank_finished_job(job_number)
		self._update_condition.release()
		return finished

	def yank_finished_job(self, job_number):
		'''
		Remove a job from the finished jobs list and return it.
		'''
		self._finished_jobs_lock.acquire()
		finished = self._finished_jobs[job_number]
		del self._finished_jobs[job_number]
		self._finished_jobs_lock.release()
		return finished

	def _job_finished(self, job_number):
		'''
		Returns true if a job is in the finished jobs list.
		'''
		self._finished_jobs_lock.acquire()
		done = (job_number in self._finished_jobs.keys())
		self._finished_jobs_lock.release()
		return done
	
	def _run_thread(self):
		'''
		Runs the job thread if it isn't already running, and only if there
		is work to be done.
		'''
		self._start_lock.acquire()
		if not self._thread or not self._thread.is_alive():
			if not self._job_queue.empty():
				self._thread = threading.Thread(target=self._job_thread)
				self._thread.start()
		self._start_lock.release()

	def _job_thread(self):
		'''
		Thread for processing conversion jobs. Only runs until
		there are no jobs left.
		'''
		while not self._job_queue.empty():
			try:
				conversion_job = self._job_queue.get(False)
			except Queue.Empty:
				# reset job numbers so they don't get crazy
				# for a long running application
				self._job_number = 0
				self._last_served = Jawed.LAST_SERVED_NONE
				break
			command = "java -jar %s %s %s" % (self.jarfile, conversion_job['in'], conversion_job['out'])
			subprocess.call(command, shell=True)
			self._update_condition.acquire()
			self._finished_jobs_lock.acquire()
			self._finished_jobs.update({conversion_job['job']:conversion_job})
			self._finished_jobs_lock.release()
			self._last_served = conversion_job['job']
			self._update_condition.notify()
			self._update_condition.release()
		
	def _get_new_job_number(self):
		old = self._job_number
		self._job_number = self._job_number + 1
		return old

class JawedTest(unittest.TestCase):
	'''
	Tests for Jawed.
	'''

	reserve = ['test.pdf', 'nothere.odt', 'nothere.pdf', 'stress']
	STRESS_FILE_COUNT = 10
	STRESS_THREAD_TIMEOUT = 300

	def setUp(self):
		self.instance = Jawed.get_instance()
		if not os.path.exists('test.odt'):
			raise IOError((errno.ENOENT, '%s (This test requires \'test.odt\' to exist in the same directory.)' % os.strerror(errno.ENOENT), 'test.odt'))
		for filename in JawedTest.reserve:
			if os.path.exists(filename):
				raise IOError((errno.EEXIST, '%s (This test would overwrite \'%s\', then delete it - please move this file to test.)' % (os.strerror(errno.EEXIST), filename), filename))
		JawedTest._make_test_stress_files()

	def tearDown(self):
		for filename in JawedTest.reserve:
			if os.path.exists(filename):
				if os.path.isfile(filename):
					os.remove(filename)
				elif os.path.isdir(filename):
					shutil.rmtree(filename)

	@staticmethod
	def _make_test_stress_files():
		'''
		Make all files required for the stress test.
		'''
		os.mkdir('stress')
		for i in range(0, JawedTest.STRESS_FILE_COUNT):
			shutil.copyfile('test.odt', 'stress/test%d.odt' % i)

	def test_conversion(self):
		'''
		Converts a single file.
		'''
		job = self.instance.queue_conversion_job('test.odt', 'test.pdf')
		self.instance.wait_for_job(job)
		self.assertTrue(os.path.exists('test.pdf'))

	def test_no_file(self):
		'''
		Raise error when file doesn't exist.
		'''
		self.assertRaises(IOError, self.instance.queue_conversion_job, 'nothere.odt', 'nothere.pdf')

	def test_stress(self):
		'''
		Tests multiple threads using Jawed concurrently.
		'''
		threads = []

		for i in range(0, JawedTest.STRESS_FILE_COUNT):
			threads.append(threading.Thread(target=self._thread_test_stress, args=[i]))
			threads[-1].start()

		for i in range(0, JawedTest.STRESS_FILE_COUNT):
			threads[i].join(JawedTest.STRESS_THREAD_TIMEOUT)
			print "Thread %s was joined" % i
			self.assertFalse(threads[i].is_alive())

	def _thread_test_stress(self, i):
		'''
		Thread for test_stress. Converts a single file and waits for the result.
		'''
		job = self.instance.queue_conversion_job('stress/test%d.odt' % i, 'stress/test%d.pdf' % i)
		while self.instance.wait_status(job) != Jawed.JOB_COMPLETE:
			pass
		self.instance.yank_finished_job(job)
		self.assertTrue(os.path.exists('stress/test%d.pdf' % i))
	
# Run tests when file is executed
if __name__ == '__main__':
	unittest.main()

