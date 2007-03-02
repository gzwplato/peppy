# peppy Copyright (c) 2006-2007 Rob McMullen
# Licenced under the GPL; see http://www.flipturn.org/peppy for more info
"""Sidebar for debug printing.

Sidebar that shows classes that have debug printing capability.

FIXME: this doesn't yet update between frames, so items may be out of
sync if this is shown on two different frames.
"""

import os

from peppy import *
from peppy.main import DebugClass
from peppy.menu import *
from peppy.trac.core import *
from peppy.buffers import *

class DebugClassList(Sidebar, debugmixin):
    """Turn debug printing on or off for the listed classes.

    This is a global plugin that is used to turn on or off debug
    printing for all the classes that subclass from L{debugmixin}.
    """
    debuglevel = 0
    
    keyword="debug_list"

    default_settings = {
        'best_width': 200,
        'best_height': 500,
        'min_width': 100,
        'min_height': 100,
        }
    
    def createWindows(self,parent):
##        self.browser=wx.TextCtrl(parent, -1, "Stuff" , style=wx.TE_MULTILINE)
        self.debuglist = DebugClass(parent)
        items = self.debuglist.getItems()
        self.list=wx.CheckListBox(parent, choices=items)
        assert self.dprint(items)
        for i in range(len(items)):
            self.list.Check(i, self.debuglist.isChecked(i))
        self.list.Bind(wx.EVT_CHECKLISTBOX, self.OnCheckListBox)
        
        paneinfo=wx.aui.AuiPaneInfo().Name(self.keyword).Caption("Debug Printing")
        paneinfo.Left()
        paneinfo.BestSize(wx.Size(self.settings.best_width,
                                  self.settings.best_height))
        paneinfo.MinSize(wx.Size(self.settings.min_width,
                                 self.settings.min_height))
        
        self.frame.addPane(self.list,paneinfo)

    def OnCheckListBox(self, evt):
        index = evt.GetSelection()
        self.debuglist.action(index)
        assert self.dprint("index=%d checked=%s" % (index, self.debuglist.isChecked(index)))
        self.list.Check(index, self.debuglist.isChecked(index))

class DebugClassProvider(Component):
    """Plugin to show all classes capable of debug printing.

    This plugin manages the debug list and the debug menu.  Note that
    if we're running in optimize mode (python -O), this plugin won't
    be active because it won't do anything.  Debug print statements
    are hidden behind asserts, and asserts are removed when running in
    optimize mode.
    """
    implements(ISidebarProvider)
    implements(IMenuItemProvider)

    use_menu = False

    def getSidebars(self):
        # Don't show the sidebar in optimize mode (__debug == False)
        if __debug__:
            yield DebugClassList
        else:
            raise StopIteration

    default_menu=((None,Menu("Debug").after("Minor Mode").before("&Help")),
                  ("Debug",MenuItem(DebugClass).first()),
                  )
    def getMenuItems(self):
        # Don't show menu if in optimize mode
        if self.use_menu and __debug__:
            for menu,item in self.default_menu:
                yield (None,menu,item)
        else:
            raise StopIteration
