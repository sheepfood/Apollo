from mythic_container.MythicCommandBase import *
import json


class GetPrivsArguments(TaskArguments):

    def __init__(self, command_line, **kwargs):
        super().__init__(command_line, **kwargs)
        self.args = []

    async def parse_arguments(self):
        if len(self.command_line) > 0:
            raise Exception("getprivs takes no command line arguments.")


class GetPrivsCommand(CommandBase):
    cmd = "getprivs"
    needs_admin = False
    help_cmd = "getprivs"
    description = "Enable as many privileges as we can on our current thread token."
    version = 2
    author = "@djhohnstein"
    argument_class = GetPrivsArguments
    attackmapping = ["T1078"]

    async def create_tasking(self, task: MythicTask) -> MythicTask:
        return task

    async def process_response(self, task: PTTaskMessageAllData, response: any) -> PTTaskProcessResponseMessageResponse:
        resp = PTTaskProcessResponseMessageResponse(TaskID=task.Task.ID, Success=True)
        return resp