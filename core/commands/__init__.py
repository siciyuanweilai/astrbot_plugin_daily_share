from .receiver import CommandTargetsService


class CommandHandler(CommandTargetsService):
    def __init__(self, plugin):
        super().__init__(plugin)
