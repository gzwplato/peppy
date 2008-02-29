# peppy Copyright (c) 2006-2008 Rob McMullen
# Licenced under the GPLv2; see http://peppy.flipturn.org for more info
"""
Python major mode.
"""

import os,struct
import keyword

import wx
import wx.stc

from peppy.yapsy.plugins import *
from peppy.actions import *
from peppy.major import *
from peppy.fundamental import *
from peppy.actions.base import *

import peppy.lib.PyParse as PyParse


_sample_file='''\
import os, sys, time
"""
Sample file to demonstrate running a python script from the editor.
"""

print "Working dir = %s" % os.getcwd()

# Default to 100 repetitions
num = 100

# If we have given it an argument using the Run With Args command, process
# it here
if len(sys.argv) > 1:
    num = int(sys.argv[1])
print "Number of times to loop: %d" % num

# Perform the loop
for x in range(num):
    print 'loop %d: blah' % x
    time.sleep(1)
'''

class SamplePython(SelectAction):
    name = "&Open Sample Python"
    tooltip = "Open a sample Python file"
    default_menu = "&Help/Samples"

    def action(self, index=-1, multiplier=1):
        self.frame.open("about:sample.py")


class ElectricColon(TextModificationAction):
    name = "Electric Colon"
    tooltip = "Indent the current line when a colon is pressed"
    key_bindings = {'default': 'S-;',} # FIXME: doesn't work to specify ':'

    @classmethod
    def worksWithMajorMode(cls, mode):
        return mode.keyword == 'Python'

    def action(self, index=-1, multiplier=1):
        s = self.mode
        style = s.GetStyleAt(s.GetSelectionEnd())
        s.BeginUndoAction()
        s.ReplaceSelection(":")
        if s.isStyleComment(style) or s.isStyleString(style):
            self.dprint("within comment or string: not indenting")
            pass
        else:
            # folding info not automatically updated after a Replace, so
            # do it manually
            linestart = s.PositionFromLine(s.GetCurrentLine())
            s.Colourise(linestart, s.GetSelectionEnd())
            s.reindentLine(dedent_only=True)
        s.EndUndoAction()


# Helper functions required by IDLE's PyParse routine
def is_char_in_string(stc, pos):
    """Return True if the position is within a string"""
    style = stc.GetStyleAt(pos)
    #dprint("style %d at pos %d" % (style, pos))
    if style == 3 or style == 7 or style == 6 or style == 4:
        return True
    return False

def build_char_in_string_func(stc, startindex):
    """Factory to create a specific is_char_in_string function that also
    includes an offset.
    """
    def inner(offset, _startindex=startindex, _stc=stc, _icis=is_char_in_string):
        #dprint("offset=%d, startindex=%d" % (offset, _startindex))
        return _icis(_stc, _startindex + offset)
    return inner


class PythonMode(JobControlMixin, SimpleFoldFunctionMatchMixin,
                 FundamentalMode):
    keyword='Python'
    icon='icons/py.png'
    regex="\.(py|pyx)$"
    
    fold_function_match = ["def ", "class "]

    default_classprefs = (
        )

    def findIndent(self, linenum, extra=None):
        """Find indentation of next line using IDLE's parsing code.
        
        @param linenum: line number
        @param extra: flag to indicate if it should return a tuple containing
        extra data
        @return: if extra is None or False, returns integer indicating number
        of columns to indent.  If extra is True, returns a tuple of the number
        of columns and a keyword indicating extra information.
        """
        indentwidth = self.GetIndent()
        tabwidth = 87
        indent = self.GetLineIndentation(linenum)
        y = PyParse.Parser(indentwidth, tabwidth)
        # FIXME: context line hack straight from IDLE
        for context in [50, 500, 5000000]:
            firstline = linenum - context
            if firstline < 0:
                firstline = 0
            start = self.PositionFromLine(firstline)
            end = self.PositionFromLine(linenum)
            rawtext = self.GetTextRange(start, end)
            
            # FIXME: for now, rather than changing PyParse, I'm converting
            # everything to newlines because PyParse is hardcoded for newlines
            # only
            if self.getLinesep() == "\r\n":
                #dprint("Converting windows!")
                rawtext = rawtext.replace("\r\n", "\n")
            elif self.getLinesep() == "\r":
                #dprint("Converting old mac!")
                rawtext = rawtext.replace("\r", "\n")
            y.set_str(rawtext+"\n")
            
            bod = y.find_good_parse_start(build_char_in_string_func(self, start))
            if bod is not None or firstline == 0:
                break
        #dprint(rawtext)
        self.dprint("bod = %s" % bod)
        y.set_lo(bod or 0)

        c = y.get_continuation_type()
        self.dprint("continuation type: %s" % c)
        extra_data = None
        if c != PyParse.C_NONE:
            # The current stmt hasn't ended yet.
            if c == PyParse.C_STRING_FIRST_LINE:
                # after the first line of a string; do not indent at all
                print "C_STRING_FIRST_LINE"
                pass
            elif c == PyParse.C_STRING_NEXT_LINES:
                # inside a string which started before this line;
                # just mimic the current indent
                #text.insert("insert", indent)
                s = self.GetStyleAt(end)
                if s == 6 or s == 7:
                    # Inside a triple quoted string (TQS)
                    print "C_STRING_NEXT_LINES in TQS"
                    indentstr = y.get_base_indent_string()
                    indent = len(indentstr.expandtabs(tabwidth))
                else:
                    # FIXME: Does this ever happen without being in a TQS???
                    print "C_STRING_NEXT_LINES"
            elif c == PyParse.C_BRACKET:
                # line up with the first (if any) element of the
                # last open bracket structure; else indent one
                # level beyond the indent of the line with the
                # last open bracket
                print "C_BRACKET"
                #self.reindent_to(y.compute_bracket_indent())
                indent = y.compute_bracket_indent()
            elif c == PyParse.C_BACKSLASH:
                # if more than one line in this stmt already, just
                # mimic the current indent; else if initial line
                # has a start on an assignment stmt, indent to
                # beyond leftmost =; else to beyond first chunk of
                # non-whitespace on initial line
                if y.get_num_lines_in_stmt() > 1:
                    pass
                else:
                    indent = y.compute_backslash_indent()
            else:
                assert 0, "bogus continuation type %r" % (c,)
                
        else:
            # This line starts a brand new stmt; indent relative to
            # indentation of initial line of closest preceding
            # interesting stmt.
            indentstr = y.get_base_indent_string()
            indent = len(indentstr.expandtabs(tabwidth))
        
            if y.is_block_opener():
                self.dprint("block opener")
                indent += indentwidth
                extra_data = "block opener"
            elif indent and y.is_block_closer():
                self.dprint("block dedent")
                indent = ((indent-1)//indentwidth) * indentwidth
                extra_data = "block dedent"
        self.dprint("indent = %d" % indent)
        if extra:
            return (indent, extra_data)
        return indent

    def getReindentColumn(self, linenum, linestart, pos, before, col, ind):
        """Use IDLE parsing module to find the correct indention for the line.
        """
        # Use the current line number, which will find the indention based on
        # the previous line
        indent, extra = self.findIndent(linenum, True)
        #dprint("linenum: %d indent=%d extra=%s" % (linenum, indent, extra))
        
        # The text begins at indpos; check some special cases to see if there
        # should be a dedent
        style = self.GetStyleAt(before)
        end = self.GetLineEndPosition(linenum)
        cmd = self.GetTextRange(before, end)
        #dprint("checking %s" % cmd)
        if linenum>0 and style==wx.stc.STC_P_WORD and (cmd.startswith('else') or cmd.startswith('elif') or cmd.startswith('except') or cmd.startswith('finally')):
            #dprint("Found a dedent: %s" % cmd)
            if extra != "block dedent":
                # If we aren't right after a return or something that already
                # caused a dedent, dedent it
                indent -= self.GetIndent()
        return indent

    def findParagraphStart(self, linenum, info):
        """Check to see if a previous line should be included in the
        paragraph match.
        """
        leader, line, trailer = self.splitCommentLine(self.GetLine(linenum))
        self.dprint(line)
        if leader != info.leader_pattern or len(line.strip())==0:
            return False
        stripped = line.strip()
        if stripped == "'''" or stripped == '"""':
            # triple quotes on line by themselves: don't include
            return False
        info.addStartLine(linenum, line)
        
        # Triple quotes embedded in the string are included, but then
        # we're done
        if line.startswith("'''") or line.startswith('"""'):
            return False
        return True
    
    def findParagraphEnd(self, linenum, info):
        """Check to see if a following line should be included in the
        paragraph match.
        """
        leader, line, trailer = self.splitCommentLine(self.GetLine(linenum))
        self.dprint(line)
        if leader != info.leader_pattern or len(line.strip())==0:
            return False
        stripped = line.strip()
        if stripped == "'''" or stripped == '"""':
            # triple quotes on line by themselves: don't include
            return False
        info.addEndLine(linenum, line)
        
        # A triple quote at the end of the line will be included in the
        # word wrap, but this ends the search
        if line.startswith("'''") or line.startswith('"""'):
            return False
        line = line.rstrip()
        if line.endswith("'''") or line.endswith('"""'):
            return False
        return True


class PythonErrorMode(FundamentalMode):
    keyword = "Python Error"
    icon='icons/error.png'
    
    default_classprefs = (
        BoolParam('line_numbers', False),
        )

    @classmethod
    def verifyMagic(cls, header):
        return header.find("Traceback (most recent call last):") >= 0


class PythonPlugin(IPeppyPlugin):
    def aboutFiles(self):
        return {'sample.py': _sample_file}
    
    def getMajorModes(self):
        yield PythonMode
        yield PythonErrorMode

    def getActions(self):
        return [SamplePython, ElectricColon]
