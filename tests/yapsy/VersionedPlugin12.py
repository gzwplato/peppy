#!/usr/bin/python
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-



"""
This is certainly the second simplest plugin ever.
"""

from peppy.yapsy.IPlugin import IPlugin

class VersionedPlugin12(IPlugin):
	"""
	Only trigger the expected test results.
	"""

	def __init__(self):
		"""
		init
		"""
		# initialise parent class
		IPlugin.__init__(self)
		print("Version 1.2")

	def activate(self):
		"""
		On activation tell that this has been successfull.
		"""
		# get the automatic procedure from IPlugin
		IPlugin.activate(self)
		print("Activated Version 1.2!")
		return


	def deactivate(self):
		"""
		On deactivation check that the 'activated' flag was on then
		tell everything's ok to the test procedure.
		"""
		IPlugin.deactivate(self)
		print("Deactivated Version 1.2!")
