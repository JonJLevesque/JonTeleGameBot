from . import brain, github, help, ideas, listener, memory, reminders, shipping, tools, wordle


def all_handlers():
    return (
        help.get_handlers()
        + ideas.get_handlers()
        + shipping.get_handlers()
        + reminders.get_handlers()
        + brain.get_handlers()
        + tools.get_handlers()
        + wordle.get_handlers()
        + github.get_handlers()
        + memory.get_handlers()
        + listener.get_handlers()
    )
