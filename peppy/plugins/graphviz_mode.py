# peppy Copyright (c) 2006-2007 Rob McMullen
# Licenced under the GPL; see http://www.flipturn.org/peppy for more info
"""Graphviz DOT Language editing support.

L{Graphviz<http://graphviz.org/>} is a high quality open source
program to automatically layout directed and undirected graphs from a
text description of the node and edge relationships.  The description
language is called L{DOT<http://graphviz.org/doc/info/lang.html>} and
in most cases is generated by a program.  It is rare to write one by
hand, but when you have to, this mode is helpful.
"""

import os,struct
import keyword
from cStringIO import StringIO

import wx
import wx.stc

from peppy.yapsy.plugins import *
from peppy.lib.bitmapscroller import *
from peppy.lib.processmanager import ProcessManager, JobOutputMixin
from peppy.menu import *
from peppy.major import *
from peppy.fundamental import FundamentalMode

from peppy.about import SetAbout

_sample_file = """\
// Sample graphviz source file
digraph G {
   Hello->World;
   peppy->"is here";
}
"""

SetAbout('sample.dot',_sample_file)


class SampleDot(SelectAction):
    name = _("&Open Sample Graphviz dot file")
    tooltip = _("Open a sample Graphviz file")
    icon = wx.ART_FILE_OPEN

    def action(self, index=-1):
        self.frame.open("about:sample.dot")



class GraphvizMode(FundamentalMode):
    """Major mode for editing Graphviz .dot files.

    Uses the C++ mode of the STC to highlight the files, since
    graphviz .dot files are similar in structure to C++ files.
    """
    keyword='Graphviz'
    icon='icons/graphviz.ico'
    regex="\.dot$"

    start_line_comment = "// "

    default_classprefs = (
        StrParam('path', '/usr/local/bin'),

        StrParam('minor_modes', 'GraphvizView'),
        StrParam('sample_file', _sample_file),
        IntParam('stc_lexer', wx.stc.STC_LEX_CPP),
        StrParam('stc_keywords', 'strict graph digraph graph node edge subgraph'),
        ReadOnlyParam('stc_boa_style_names', {wx.stc.STC_C_DEFAULT: 'Default',
                                wx.stc.STC_C_COMMENT: 'Comment',
                                wx.stc.STC_C_COMMENTLINE: 'Comment line',
                                wx.stc.STC_C_COMMENTDOC: 'Comment doc',
                                wx.stc.STC_C_NUMBER: 'Number',
                                wx.stc.STC_C_WORD: 'Keyword',
                                wx.stc.STC_C_STRING: 'String',
                                wx.stc.STC_C_PREPROCESSOR: 'Preprocessor',
                                wx.stc.STC_C_OPERATOR: 'Operator',
                                wx.stc.STC_C_STRINGEOL: 'EOL unclosed string',
                                }),
        ReadOnlyParam('stc_lexer_styles', {wx.stc.STC_C_COMMENTLINE: wx.stc.STC_C_COMMENT,
                             wx.stc.STC_C_COMMENTDOC: wx.stc.STC_C_COMMENT,
                             wx.stc.STC_C_NUMBER: 'fore:#0076AE',
                             wx.stc.STC_C_WORD: 'bold,fore:#004080',
                             wx.stc.STC_C_STRING: 'fore:#800080',
                             wx.stc.STC_C_PREPROCESSOR: 'fore:#808000',
                             wx.stc.STC_C_OPERATOR: 'bold',
                             wx.stc.STC_C_STRINGEOL: 'back:#FFD5FF',
                             }),
        )
    


class GraphvizViewMinorMode(MinorMode, JobOutputMixin, wx.Panel, debugmixin):
    """Display the graphical view of the DOT file.

    This displays the graphic image that is represented by the .dot
    file.  It calls the external graphviz program and displays a
    bitmap version of the graph.
    """
    debuglevel = 0

    keyword="GraphvizView"
    default_classprefs = (
        IntParam('best_width', 300),
        IntParam('best_height', 300),
        IntParam('min_width', 300),
        IntParam('min_height', 300),
        )

    dotprogs = ['dot', 'neato', 'twopi', 'circo', 'fdp']

    def __init__(self, major, parent):
        wx.Panel.__init__(self, parent)
        self.major = major

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.prog = wx.Choice(self, -1, (100, 50), choices = self.dotprogs)
        self.prog.SetSelection(0)
        buttons.Add(self.prog, 1, wx.EXPAND)
        
        self.regen = wx.Button(self, -1, "Regenerate")
        self.regen.Bind(wx.EVT_BUTTON, self.OnRegenerate)
        buttons.Add(self.regen, 1, wx.EXPAND)

        self.sizer.Add(buttons)

        self.preview = None
        self.drawing = BitmapScroller(self)
        self.sizer.Add(self.drawing, 1, wx.EXPAND)

        self.process = None
        self.Bind(wx.EVT_IDLE, self.OnIdle)
        self.Bind(wx.EVT_SIZE, self.OnSize)

        self.Layout()

    def deletePreHook(self):
        if self.process is not None:
            self.process.kill()

    def busy(self, busy):
        if busy:
            cursor = wx.StockCursor(wx.CURSOR_WATCH)
        else:
            cursor = wx.StockCursor(wx.CURSOR_DEFAULT)
        self.SetCursor(cursor)
        self.drawing.SetCursor(cursor)
        self.regen.SetCursor(cursor)
        self.regen.Enable(not busy)
        self.prog.SetCursor(cursor)
        self.prog.Enable(not busy)

    def OnRegenerate(self, event):
        prog = os.path.normpath(os.path.join(self.major.classprefs.path,self.prog.GetStringSelection()))
        assert self.dprint("using %s to run graphviz" % repr(prog))

        cmd = "%s -Tpng" % prog

        ProcessManager().run(cmd, self, self.major.buffer.stc.GetText())

    def startupCallback(self, job):
        self.process = job
        self.busy(True)
        self.preview = StringIO()

    def stdoutCallback(self, job, text):
        self.preview.write(text)

    def OnIdle(self, evt):
        ProcessManager().idle()
        evt.Skip()

    def finishedCallback(self, job):
        assert self.dprint()
        self.process = None
        self.busy(False)
        self.createImage()
        # Don't call evt.Skip() here because it causes a crash

    def createImage(self):
        assert self.dprint("using image, size=%s" % len(self.preview.getvalue()))
        if len(self.preview.getvalue())==0:
            self.major.frame.SetStatusText("Error running graphviz!")
            return
        
##        fh = open("test.png",'wb')
##        fh.write(self.preview.getvalue())
##        fh.close()
        fh = StringIO(self.preview.getvalue())
        img = wx.EmptyImage()
        if img.LoadStream(fh):
            self.bmp = wx.BitmapFromImage(img)
            self.major.frame.SetStatusText("Graphviz completed.")
        else:
            self.bmp = None
            self.major.frame.SetStatusText("Invalid image")
        self.drawing.setBitmap(self.bmp)

    def OnSize(self, evt):
        self.Refresh()
        evt.Skip()
        



class GraphvizPlugin(IPeppyPlugin):
    """Graphviz plugin to register modes and user interface.
    """
    def possibleModes(self):
        yield GraphvizMode

    def getMinorModes(self):
        yield GraphvizViewMinorMode
    
    default_menu=((None,(_("&Help"),_("&Samples")),MenuItem(SampleDot)),
                  )
    def getMenuItems(self):
        for mode,menu,item in self.default_menu:
            yield (mode,menu,item)

