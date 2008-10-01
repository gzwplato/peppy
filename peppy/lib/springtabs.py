#-----------------------------------------------------------------------------
# Name:        springtabs.py
# Purpose:     Tab-bar control that pops up windows when clicked
#
# Author:      Rob McMullen
#
# Created:     2008
# RCS-ID:      $Id: $
# Copyright:   (c) 2007 Rob McMullen
# License:     wxWidgets
#-----------------------------------------------------------------------------
"""SpringTabs

This module provides popup windows from a group of tabs

"""

import os, sys, struct, Queue, threading, time, socket
from cStringIO import StringIO

import wx
import wx.stc
from wx.lib.pubsub import Publisher
from wx.lib.evtmgr import eventManager
from wx.lib.buttons import GenToggleButton

try:
    from peppy.debug import *
except:
    def dprint(txt=""):
        print txt


class FakePopupWindow(wx.MiniFrame):
    def __init__(self, parent, style=None):
        super(FakePopupWindow, self).__init__(parent, style = wx.NO_BORDER |wx.FRAME_FLOAT_ON_PARENT
                              | wx.FRAME_NO_TASKBAR)
        #self.Bind(wx.EVT_KEY_DOWN , self.OnKeyDown)
        self.Bind(wx.EVT_CHAR, self.OnChar)
        self.Bind(wx.EVT_SET_FOCUS, self.OnFocus)
    
    def OnChar(self, evt):
        #print("OnChar: keycode=%s" % evt.GetKeyCode())
        self.GetParent().GetEventHandler().ProcessEvent(evt)

    def Position(self, position, size):
        #print("pos=%s size=%s" % (position, size))
        self.Move((position[0]+size[0], position[1]+size[1]))
        
    def SetPosition(self, position):
        #print("pos=%s" % (position))
        self.Move((position[0], position[1]))
        
    def ActivateParent(self):
        """Activate the parent window
        @postcondition: parent window is raised

        """
        parent = self.GetParent()
        parent.Raise()
        parent.SetFocus()

    def OnFocus(self, evt):
        """Raise and reset the focus to the parent window whenever
        we get focus.
        @param evt: event that called this handler

        """
        print("On Focus: set focus to %s" % str(self.GetParent()))
        self.ActivateParent()
        evt.Skip()



class SpringTabItemRenderer(object):
    def OnPaint(self, item, evt):
        (width, height) = item.GetClientSizeTuple()
        x1 = y1 = 0
        x2 = width-1
        y2 = height-1

        dc = wx.PaintDC(item)
        if item.hover:
            self.DrawHoverBackground(item, dc)
        else:
            brush = item.GetBackgroundBrush(dc)
            if brush is not None:
                dc.SetBackground(brush)
                dc.Clear()

        item.DrawLabel(dc, width, height)
        self.DrawHoverDecorations(item, dc, width, height)
        
        dprint("button %s: pressed=%s" % (item.GetLabel(), not item.up))
    
    def DrawHoverBackground(self, item, dc):
        brush = wx.Brush(item.faceDnClr, wx.SOLID)
        dc.SetBackground(brush)
        dc.Clear()

    def DrawHoverDecorations(self, item, dc, width, height):
        pass


class SpringTabItemVerticalRenderer(SpringTabItemRenderer):
    def DoGetBestSize(self, item):
        """
        Overridden base class virtual.  Determines the best size of the
        button based on the label and bezel size.
        """
        h, w, useMin = item._GetLabelSize()
        width = w + item.border + item.bezelWidth - 1
        height = h + item.border + item.bezelWidth - 1
        #dprint("width=%d height=%d" % (width, height))
        return (width, height)

    def DrawLabel(self, item, dc, width, height, dx=0, dy=0):
        dc.SetFont(item.GetFont())
        if item.IsEnabled():
            dc.SetTextForeground(item.GetForegroundColour())
        else:
            dc.SetTextForeground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        label = item.GetLabel()
        th, tw = dc.GetTextExtent(label)
        #dc.DrawText(label, (width-tw)/2+dx, (height-th)/2+dy)
        dc.DrawRotatedText(label, (width-tw)/2+dx, height+dy, 90.0)


class SpringTabItem(GenToggleButton):
    def __init__(self, parent, id=-1, label='', **kwargs):
        self.border = 6
        self.hover = False
        
        GenToggleButton.__init__(self, parent, id, label)
        self.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnLeave)
    
    def InitColours(self):
        faceClr = self.GetBackgroundColour()
        r, g, b = faceClr.Get()
        fr, fg, fb = max(0,r-32), max(0,g-32), max(0,b-32)
        dprint(str((fr, fg, fb)))
        self.faceDnClr = wx.Colour(fr, fg, fb)
        sr, sg, sb = max(0,r-32), max(0,g-32), max(0,b-32)
        self.shadowPen = wx.Pen(wx.Colour(sr,sg,sb), 1, wx.SOLID)
        hr, hg, hb = min(255,r+64), min(255,g+64), min(255,b+64)
        self.highlightPen = wx.Pen(wx.Colour(hr,hg,hb), 1, wx.SOLID)
        self.focusClr = wx.Colour(hr, hg, hb)
    
    def DoGetBestSize(self):
        return self.GetParent().getRenderer().DoGetBestSize(self)

    def DrawLabel(self, dc, width, height, dx=0, dy=0):
        self.GetParent().getRenderer().DrawLabel(self, dc, width, height, dx, dy)
    
    def OnPaint(self, evt):
        self.GetParent().getRenderer().OnPaint(self, evt)
    
    def SetToggle(self, flag, check_popup=True):
        self.up = not flag
        if check_popup:
            self.GetParent().setRadio(self)
        self.Refresh()

    def OnLeftDown(self, event):
        if not self.IsEnabled():
            return
        self.saveUp = self.up
        self.up = not self.up
        self.GetParent().setRadio(self)
        self.CaptureMouse()
        self.SetFocus()
        self.Refresh()

    def OnEnter(self, evt):
        self.hover = True
        self.Refresh()
    
    def OnLeave(self, evt):
        self.hover = False
        self.Refresh()


class SpringTabs(wx.Panel):
    def __init__(self, parent, *args, **kwargs):
        wx.Panel.__init__(self, parent, *args, **kwargs)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        
        self._tabs = []
        self._tab_renderer = SpringTabItemVerticalRenderer()
        self._radio = None

        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
    
    def getRenderer(self):
        return self._tab_renderer
    
    def setRadio(self, item):
        self._processing_radio = True
        for tab in self._tabs:
            if tab != item and tab.GetToggle():
                tab.SetToggle(False, check_popup=False)
        if self._radio != item:
            self.popdownItem(self._radio)
            self.popupItem(item)
        elif not item.GetToggle():
            self.popdownItem(item)
    
    def popupItem(self, item):
        self._radio = item
        dprint("Popping up %s" % item.GetLabel())
    
    def popdownItem(self, item):
        if self._radio is not None:
            dprint("Removing popup %s" % self._radio.GetLabel())
        self._radio = None
    
    def OnPaint(self, evt):
        dc = wx.PaintDC(self)
        
        size = self.GetClientSize()
        dc.SetFont(wx.NORMAL_FONT)
        dc.SetBrush(wx.WHITE_BRUSH)
        dc.SetPen(wx.WHITE_PEN)
        dc.DrawRectangle(0, 0, size.x, size.y)
        dc.SetPen(wx.LIGHT_GREY_PEN)
        dc.DrawLine(0, 0, size.x, size.y)
        dc.DrawLine(0, size.y, size.x, 0)
        
        #self._tab_renderer.drawTabs(dc, size.x, self._tabs)
        evt.Skip()


    def OnEraseBackground(self, evt):
        # intentionally empty
        pass

    def OnSize(self, evt):
        self.Refresh()
        evt.Skip()

    def addTab(self, title, window):
        tab = SpringTabItem(self, label=title, window=window)
        self.GetSizer().Add(tab, 0, wx.EXPAND)
        self._tabs.append(tab)
        
        self.Refresh()





if __name__ == "__main__":
    app = wx.PySimpleApp()
    frm = wx.Frame(None,-1,"Test",style=wx.TAB_TRAVERSAL|wx.DEFAULT_FRAME_STYLE,
                   size=(300,300))
    panel = wx.Panel(frm)
    sizer = wx.BoxSizer(wx.HORIZONTAL)
    tabs = SpringTabs(panel)
    tabs.addTab("One", None)
    tabs.addTab("Two", None)
    tabs.addTab("Three", None)
    sizer.Add(tabs, 0, wx.EXPAND)
    text = wx.StaticText(panel, -1, "Just a placeholder here.  The real action is to the left!")
    sizer.Add(text, 1, wx.EXPAND)
    
    panel.SetAutoLayout(True)
    panel.SetSizer(sizer)
    #sizer.Fit(panel)
    #sizer.SetSizeHints(panel)
    panel.Layout()
    app.SetTopWindow(frm)
    frm.Show()
    app.MainLoop()
