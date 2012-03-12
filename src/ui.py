import urwid
import debugger
from debugger import LineBreakPoint
class CursesUI:
    """
    A curses UI for the debugger.
    """
    def __init__(self):
        self.debugger = None
        self.currentMessage = ""
        self.messageBox = urwid.Text(self.currentMessage)
        self.content = urwid.SimpleListWalker([])
        self.input = urwid.Edit()
        self.content_length = 0
        self.stateMachine = StateMachine(self)
        self.stateMachine.add_mode(OpenFileMode(self))
        self.stateMachine.add_mode(FileExplorerMode(self))
        self.stateMachine.add_mode(ExitMode(self))
        self.stateMachine.add_mode(RunMode(self))
        self.file_loaded = False
        self.focus = 0;

    def set_debugger(self, debugger):
        self.debugger = debugger # Maybe move to the constructor?

    def menu(self):
        menu = []
        for item in ["(O)pen file", "(E)xit", "<SPACE> Set breakpoint", "(R)un"]:
            menu.append(urwid.Text(item))
        return menu
    def print_message(self, message):
        self.currentMessage = message
        self.messageBox.set_text(self.currentMessage)

    def print_file(self, file_name, content, breakpoints = {}):
        del self.content[:]
        lines = content.split('\n')
        for line in lines:
            text_line = urwid.Text(line)
            # @todo: This is pretty crappy, we should create our own widget.
            text_line._selectable = True
            text_line.keypress = self.line_press
            self.content.append(urwid.AttrMap(text_line, None, 'reveal focus'))
        self.content_length = len(lines)
        self.file_loaded = True
        self.file_name = file_name
    
    def line_press(self, size, key):
        focus = self.content.get_focus()[1]
        if key == "down" and len(self.content) < focus:
            self.content.set_focus(self.content.get_next(focus)[1])
        if key == "up" and focus > 0:
            self.content.set_focus(focus)
        return key
    
    def trigger_breakpoint(self, line):
        line -= 1
        if line < self.content_length:
            self.content[line].set_attr_map({ None: 'triggered' })

    def start(self):
        palette = [('header', 'white', 'black'),
                   ('reveal focus', 'black', 'dark cyan', 'standout'),
                   ('streak', 'black', 'dark red', 'standout'),
                   ('triggered', 'black', 'dark green', 'standout')]
        head = urwid.AttrMap(self.messageBox, 'header')
        columns = urwid.Columns(self.menu())
        footer = urwid.Pile([columns, self.input])
        self.listbox = urwid.ListBox(self.content)
        self.frame = urwid.Frame(self.listbox, head, footer)
        self.loop = urwid.MainLoop(self.frame, palette, unhandled_input=self.stateMachine.handle_input)
        self.stateMachine.evaluate_modes()
        self.loop.run()

    def stop(self):
        self.run = False


class StateMachine:
    """
    This simple state machine keeps track of what mode we are currently in.
    """
    def __init__(self, ui):
        self.ui = ui
        self.modes = []
        self.current_mode = None
    
    def add_mode(self, mode):
        self.modes.append(mode)

    def remove_mode(self, mode):
        self.modes.remove(mode)
  
    def evaluate_modes(self, text=None):
        for mode in self.modes:
            if mode.evaluate(text):
                self.set_mode(mode)
                break

    def handle_input(self, text):
        if not self.current_mode or not self.current_mode.locked():
            self.evaluate_modes(text)
        if self.current_mode and hasattr(self.current_mode, "handle_input") and callable(getattr(self.current_mode, "handle_input")):
            self.current_mode.handle_input(text)

    def set_previous_mode(self):
        self.current_mode = self.previous_mode
        
    def set_mode(self, mode):
        self.previous_mode= self.current_mode
        self.current_mode = mode
        # If the class has a method called enter, go ahead and call it.
        if hasattr(mode, "enter") and callable(getattr(mode, "enter")):
            self.current_mode.enter(self)
        

class Mode:
    def __init__(self, ui):
        self.ui = ui
    
    def locked(self):
        return False

class ExitMode(Mode):
    def __init__(self, ui):
        self.ui = ui
        
    def evaluate(self, text):
        return text == 'x'
    
    def enter(self, stateMachine):
        raise urwid.ExitMainLoop()
        self.stop()        

    def __str__(self):
        return "ExitMode"
    
class RunMode(Mode):
    def __init__(self, ui):
        self.ui = ui
        
    def evaluate(self, text):
        return text == 'r' and self.ui.debugger.is_connected()
    
    def enter(self, stateMachine):
        self.ui.debugger.execute_operation(debugger.RunOperation(self.ui.debugger))

    def __str__(self):
        return "RunMode"

class FileExplorerMode(Mode):
    def __init__(self, ui):
        self.ui = ui

    def evaluate(self, text):
        return self.ui.frame.focus_part == 'body' and (not text or text == 'down' or text == 'up' or text == ' ') and self.ui.file_loaded
    
    def handle_input(self, text):
        if text == ' ':
            focused, position = self.ui.content.get_focus()
            focused.set_attr_map({ None: 'streak' })
            position += 1
            self.ui.debugger.add_breakpoint(debugger.LineBreakPoint(self.ui.file_name, position))
            self.ui.print_message("Breakpoint set at line {0}".format(position))
    
    def __str__(self):
        return "FileExplorerMode"

class OpenFileMode(Mode):
    """
    This mode handles input of a file path. It then finished by opening it and,
    then switches to the previous mode.
    """
    def __init__(self, ui):
        self.ui = ui
    
    def evaluate(self, text):
        return text == "o"
    
    def locked(self):
        """
        This mode is locked until it releases itself.
        """
        return True
    
    def enter(self, state_machine):
        self.machine = state_machine
        self.ui.input.set_caption(u"Path to file:")
        self.ui.frame.set_focus('footer')
        urwid.connect_signal(self.ui.input, 'change', self.handle_text_input)
    
    def handle_text_input(self, edit, text):
        assert edit is self.ui.input
        self.file = text
        
    def handle_input(self, text):
        if text == "enter":
            # When we catch an enter command, swap the focus.
            self.ui.frame.set_focus('body')
            self.ui.print_file(self.file, self.ui.debugger.open_file(self.file, True), {})
            self.ui.input.set_caption(u"")
            self.ui.input.set_edit_text(u"")
            self.ui.print_message("Opened file {0}".format(self.file))
            self.machine.set_previous_mode()

    def __str__(self):
        return "OpenFileMode"