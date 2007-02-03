import os

import wx
import wx.stc as stc

from menu import *
from buffers import *
from major import *
from plugin import *
from debug import *

from actions.minibuffer import *
from actions.gotoline import *
from actions.pypefind import *

class OpenFundamental(SelectAction):
    name = "&Open Sample Text"
    tooltip = "Open some sample text"
    icon = wx.ART_FILE_OPEN

##    def isEnabled(self):
##        return not self.frame.isOpen()

    def action(self, pos=-1):
        self.dprint("id=%x name=%s pos=%s" % (id(self),self.name,str(pos)))
        self.frame.open("about:demo.txt")

class WordWrap(ToggleAction):
    name = "&Word Wrap"
    tooltip = "Toggle word wrap in this view"
    icon = wx.ART_TOOLBAR

    def isChecked(self):
        viewer=self.frame.getActiveMajorMode()
        if viewer:
            return viewer.settings.wordwrap
        return False
    
    def action(self, pos=-1):
        self.dprint("id=%x name=%s" % (id(self),self.name))
        viewer=self.frame.getActiveMajorMode()
        if viewer:
            viewer.setWordWrap(not viewer.settings.wordwrap)
    
class LineNumbers(ToggleAction):
    name = "&Line Numbers"
    tooltip = "Toggle line numbers in this view"
    icon = wx.ART_TOOLBAR

    def isChecked(self):
        viewer=self.frame.getActiveMajorMode()
        if viewer:
            return viewer.settings.linenumbers
        return False
    
    def action(self, pos=-1):
        self.dprint("id=%x name=%s" % (id(self),self.name))
        viewer=self.frame.getActiveMajorMode()
        if viewer:
            viewer.setLineNumbers(not viewer.settings.linenumbers)
    
class BeginningOfLine(SelectAction):
    name = "Cursor to Start of Line"
    tooltip = "Move the cursor to the start of the current line."
    keyboard = 'C-A'

    def action(self, pos=-1):
        self.dprint("id=%x name=%s pos=%s" % (id(self),self.name,str(pos)))
        viewer=self.frame.getActiveMajorMode()
        if viewer:
            s=viewer.stc
            pos = s.GetCurrentPos()
            col = s.GetColumn(pos)
            s.GotoPos(pos-col)
        

class EndOfLine(SelectAction):
    name = "Cursor to End of Line"
    tooltip = "Move the cursor to the end of the current line."
    keyboard = 'C-E'

    def action(self, pos=-1):
        self.dprint("id=%x name=%s pos=%s" % (id(self),self.name,str(pos)))
        viewer=self.frame.getActiveMajorMode()
        if viewer:
            s=viewer.stc
            line = s.GetCurrentLine()
            s.GotoPos(s.GetLineEndPosition(line))




class FundamentalMode(MajorMode):
    """
    The base view of most (if not all) of the views that use the STC
    to directly edit the text.  Views (like the HexEdit view or an
    image viewer) that only use the STC as the backend storage are
    probably not based on this view.
    """
    pluginkey = 'fundamental'
    keyword='Fundamental'
    regex=".*"
    lexer=stc.STC_LEX_NULL

    def createEditWindow(self,parent):
        self.dprint("creating new Fundamental window")
        self.createSTC(parent,style=True)
        win=self.stc
        win.Bind(wx.EVT_KEY_DOWN, self.frame.OnKeyPressed)
        return win

    def createSTC(self,parent,style=False):
        self.stc=MySTC(parent,refstc=self.buffer.stc)
        self.applyDefaultStyle()
        self.setLexer()
        if style:
            self.styleSTC()

    def createWindowPostHook(self):
        # SetIndent must be called whenever a new document is loaded
        # into the STC
        self.stc.SetIndent(4)
        #self.dprint("indention=%d" % self.stc.GetIndent())

        self.stc.SetIndentationGuides(1)

    def setLexer(self):
        self.stc.SetLexer(self.lexer)
        keylist=self.getKeyWords()
        for keyset,keywords in keylist:
            self.stc.SetKeyWords(keyset, keywords)

    def getKeyWords(self):
        """
        Return a list of tuples that specify the keyword set and the
        list of keywords for that set.  The STC can handle multiple
        sets of keywords in certain cases (HTML, CPP, others: see
        L{http://www.yellowbrain.com/stc/lexing.html#setkw})

        Keywords should be space separated.

        @return: list of tuples
        @rtype: list of (int, keywords)
        """
        return [(0,"")]

    def applyDefaultStyle(self):
        face1 = 'Arial'
        face2 = 'Times New Roman'
        face3 = 'Courier New'
        pb = 10

        # make some styles
        self.stc.StyleSetSpec(stc.STC_STYLE_DEFAULT, "size:%d,face:%s" % (pb, face3))
        self.stc.StyleClearAll()

        # line numbers in the margin
        self.stc.StyleSetSpec(stc.STC_STYLE_LINENUMBER, "size:%d,face:%s" % (pb, face1))
        if self.settings.linenumbers:
            self.stc.SetMarginType(0, stc.STC_MARGIN_NUMBER)
            self.stc.SetMarginWidth(0, self.settings.linenumber_margin_width)
        else:
            self.stc.SetMarginWidth(0,0)
            
        # turn off symbol margin
        if self.settings.symbols:
            self.stc.SetMarginWidth(1, self.settings.symbols_margin_width)
        else:
            self.stc.SetMarginWidth(1, 0)

        # turn off folding margin
        if self.settings.folding:
            self.stc.SetMarginWidth(2, self.settings.folding_margin_width)
        else:
            self.stc.SetMarginWidth(2, 0)

        self.setWordWrap()

    def setWordWrap(self,enable=None):
        if enable is not None:
            self.settings.wordwrap=enable
        if self.settings.wordwrap:
            self.stc.SetWrapMode(stc.STC_WRAP_CHAR)
            self.stc.SetWrapVisualFlags(stc.STC_WRAPVISUALFLAG_END)
        else:
            self.stc.SetWrapMode(stc.STC_WRAP_NONE)

    def setLineNumbers(self,enable=None):
        if enable is not None:
            self.settings.linenumbers=enable
        if self.settings.linenumbers:
            self.stc.SetMarginType(0, stc.STC_MARGIN_NUMBER)
            self.stc.SetMarginWidth(0,  self.settings.linenumber_margin_width)
        else:
            self.stc.SetMarginWidth(0,0)

    def styleSTC(self):
        pass


class FundamentalPlugin(MajorModeMatcherBase,debugmixin):
    implements(IMajorModeMatcher)
    implements(IMenuItemProvider)
    implements(IKeyboardItemProvider)
    
    def scanMagic(self,buffer):
        """
        If the buffer looks like it is a text file, flag it as a
        potential Fundamental.
        """
        if not buffer.guessBinary:
            return MajorModeMatch(FundamentalMode,generic=True)
        return None

    default_menu=((None,None,Menu("Test").after("Minor Mode")),
                  (None,"Test",MenuItem(OpenFundamental).first()),
                  ("Fundamental","Edit",MenuItem(WordWrap)),
                  ("Fundamental","Edit",MenuItem(LineNumbers)),
                  ("Fundamental","Edit",MenuItem(FindText)),
                  ("Fundamental","Edit",MenuItem(ReplaceText)),
                  ("Fundamental","Edit",MenuItem(GotoLine)),
                  )
    def getMenuItems(self):
        for mode,menu,item in self.default_menu:
            yield (mode,menu,item)

    default_keys=(("Fundamental",BeginningOfLine),
                  ("Fundamental",EndOfLine),
                  )
    def getKeyboardItems(self):
        for mode,action in self.default_keys:
            yield (mode,action)


if __name__ == "__main__":
    app=testapp(0)
    frame=RootFrame(app.main)
    frame.Show(True)
    app.MainLoop()

